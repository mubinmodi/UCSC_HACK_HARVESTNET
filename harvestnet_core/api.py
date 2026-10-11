"""Real record-backed operations at the agreed public API paths."""
from collections import deque
import copy
from datetime import datetime, timedelta, timezone
import secrets
import time
from urllib.parse import urlsplit, parse_qs
from harvestnet_agents import front_desk as desk
from .engine import Engine, jsonable
from . import changes
from .protocol import Conflict, dt, terms_hash, named, number
from .records import NotFound
from .contact import email_address


class Unauthorized(ValueError):
    pass


# Every operation this API serves, for GET /. The first block is the agreed contract
# (docs/contracts/public-api.md); the last three are additive and proposed, pending #1.
OPERATIONS = (
    ('get_health', 'GET', '/health', 'agreed'),
    ('get_fair_share', 'GET', '/fair-share', 'agreed'),
    ('preview_request', 'POST', '/requests/preview', 'agreed'),
    ('create_request', 'POST', '/requests', 'agreed'),
    ('list_food_banks', 'GET', '/food-banks', 'agreed'),
    ('choose_food_banks', 'PUT', '/requests/{request_code}/food-banks', 'agreed'),
    ('get_request', 'GET', '/requests/{request_code}', 'agreed'),
    ('release_pickup', 'POST', '/pickups/{pickup_id}/release', 'agreed'),
    ('list_produce_profiles', 'GET', '/produce-profiles', 'agreed'),
    ('create_surplus_offer', 'POST', '/surplus-offers', 'agreed'),
    ('get_lot', 'GET', '/lots/{lot_id}', 'agreed'),
    ('list_lot_versions', 'GET', '/lots/{lot_id}/versions', 'agreed'),
    ('get_food_bank_dashboard', 'GET', '/food-banks/{food_bank_id}/dashboard', 'agreed'),
    ('update_food_bank_status', 'PUT', '/food-banks/{food_bank_id}/status', 'agreed'),
    ('submit_counter', 'POST', '/lots/{lot_id}/counters', 'agreed'),
    ('confirm_pickup', 'POST', '/pickup-confirmations', 'agreed'),
    ('voice_intake', 'POST', '/voice-intake', 'agreed'),
    ('list_approvals', 'GET', '/approvals', 'agreed'),
    ('record_approval', 'POST', '/approvals', 'agreed'),
    ('get_results', 'GET', '/results', 'agreed'),
    ('record_condition_check', 'POST', '/lots/{lot_id}/condition-checks', 'proposed'),
    ('get_holding', 'GET', '/lots/{lot_id}/holding', 'proposed'),
    ('propose_change', 'POST', '/lots/{lot_id}/changes', 'proposed'),
)

# The public API contract this serves. v0.2: households give an optional email, not a phone.
CONTRACT_VERSION = "contract-v0.2"

# Voice intake calls per process in a sliding window (#22). Each call can cost a model call.
VOICE_RATE_LIMIT = (20, 60.0)

# What a household sees after "Can't make it", in its own language (ticket #6).
RELEASED_MESSAGE = {
    'en': "Thanks for telling us. Your portion will go to another family.",
    'es': "Gracias por avisarnos. Su porción pasará a otra familia.",
}
SAVED_MESSAGE = {
    'en': "Your food banks are saved.",
    'es': "Sus bancos de alimentos están guardados.",
}


class API:
    def __init__(self, engine, *, clock=None, staff_tokens=None, extractor=None, voice_rate_limit=VOICE_RATE_LIMIT, monotonic=time.monotonic,
                 household_page_url=None):
        self.engine=engine
        self.records=engine.records
        self.clock=clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.tokens=staff_tokens or {}
        if len(set(self.tokens.values())) != len(self.tokens) or any(not v for v in self.tokens.values()):
            raise ValueError("each organization needs its own nonempty token")
        if isinstance(extractor, desk.ClaudeExtractor):
            # A paid model call per transcript needs a hard cap (#22).
            raise ValueError("a Claude extractor needs a spending cap: wrap it in harvestnet_core.voice.CappedExtractor")
        self.extractor=extractor
        limit,window=voice_rate_limit
        if isinstance(limit,bool) or not isinstance(limit,int) or limit<1:
            raise ValueError("voice rate limit must be a positive whole number of calls")
        self.voice_limit,self.voice_window=limit,number(window)
        if self.voice_window<=0:
            raise ValueError("voice rate window must be positive seconds")
        self.monotonic=monotonic
        self.voice_calls=deque()
        self.household_page_url=household_page_url
        self.email_dispatcher_thread=None
        if household_page_url:
            self.records.enable_email_outbox()

    def authorize(self, owner, token):
        expected=self.tokens.get(owner)
        if not expected or not secrets.compare_digest(token or "",expected):
            raise Unauthorized("organization staff authentication required")

    def purge(self):
        with self.records.transaction():
            for lot in self.records.all('lot'):
                if lot['status'] not in ('committed','unclaimed') and dt(lot['draft']['deadline'])<=dt(self.engine.now):
                    lot.update(status='unclaimed',holds={},stop_reason='Deadline passed without every exact-version approval; nothing auto-committed')
                    self.records.put('lot',lot['draft']['lot_id'],lot)
                    self.records.event(lot['draft']['lot_id'],self.engine.now,'deadline_unclaimed',{'reason':lot['stop_reason']})
        expired=[r for r in self.records.all("request") if dt(r["expires_at"])<=dt(self.engine.now)]
        if expired:
            with self.records.transaction():
                for r in expired:
                    code=r["request_code"]
                    self.records.delete("request",code)
                    self.records.delete("email",code)
                    self.records.delete("phone",code)  # retired with contract-v0.2; kept so old records still go
                    for p in self.records.all("pickup"):
                        if p["request_code"]==code:
                            self.records.delete("pickup",p["pickup_id"])
                    # Design section 12: results keep only counts. Pickup notices keep the
                    # pounds and food bank; the request code and household window go.
                    for e in self.records.events_of_kind("pickup_notice"):
                        if e["data"].get("request_code")==code:
                            self.records.replace_event_data(e["sequence"],{**e["data"],"request_code":None,"window":None,"anonymized":"request expired"})

    def call(self, method, target, body=None, token=None):
        # Reads and mutations share one lock; never leak database exception contents.
        with self.records.lock:
            self.engine.now=self.clock()
            self.purge()
            try:
                status,data=self.dispatch(method,target,body or {},token)
                return status,{"mode":self.engine.fixture["mode"],"synthetic":self.engine.fixture["synthetic"],**data}
            except Unauthorized as exc:
                return 401,{"error":{"code":"unauthorized","message":str(exc)}}
            except NotFound:
                return 404,{"error":{"code":"not_found","message":"Record not found"}}
            except Conflict as exc:
                return 409,{"error":{"code":"conflict","message":str(exc)}}
            except KeyError as exc:
                # A missing field, or an unknown produce or organization in the body: bad input.
                return 400,{"error":{"code":"bad_request","message":f"missing or unknown field {exc}"}}
            except (ValueError,TypeError,AttributeError) as exc:
                return 400,{"error":{"code":"bad_request","message":str(exc)}}

    def preview(self, draft):
        return {"saved":False,"draft_request":draft.to_dict(),"complete":draft.is_complete,"fair_share_lb":self.engine.calc.fair_share(draft.household_size).pounds if draft.household_size else None,"read_back":desk.read_back(draft),"missing_questions":list(desk.missing_questions(draft)),"consent_question":desk.consent_wording(draft) if draft.is_complete else None}

    def item_name(self,produce_id,language):
        """The produce name a household sees, in its language (ticket #6). Spanish names come
        from the reviewed produce profiles; an item without one keeps its English name."""
        profile=self.engine.calc.profiles.get(produce_id)
        try:
            return profile.display_name(language)
        except KeyError:
            return profile.name

    def wording(self,p,r,language=None):
        language=desk.Language(language or r["language"])
        window=p["window"]
        portions=[desk.ProducePortion(self.item_name(i["produce_id"],language.value).lower(),i["pounds"],"committed") for i in p["items"]]
        facts=desk.PickupFacts(p["food_bank_name"],dt(window["start"]).time(),dt(window["end"]).time(),r["request_code"],portions,r.get("received_this_week_lb",0),r["fair_share_lb"])
        return desk.pickup_wording(facts,language)

    def voice_allowed(self):
        """A per-process sliding-window rate limit; one process is one counter."""
        now=self.monotonic()
        while self.voice_calls and now-self.voice_calls[0]>=self.voice_window:
            self.voice_calls.popleft()
        if len(self.voice_calls)>=self.voice_limit:
            return False
        self.voice_calls.append(now)
        return True

    def drop_off(self, raw):
        """This offer's own drop-off ability, checked. ``None`` means the donor can't drop off."""
        if not isinstance(raw,dict):
            raise ValueError("drop_off must be an object")
        can=raw.get('can_drop_off',True)
        if type(can) is not bool:
            raise ValueError("drop_off.can_drop_off must be true or false")
        if not can:
            return None
        window=raw['window']
        if dt(window['start'])>=dt(window['end']):
            raise ValueError("drop-off window must end after it starts")
        if type(raw.get('refrigerated',False)) is not bool:
            raise ValueError("drop_off.refrigerated must be true or false")
        ids=raw['food_bank_ids']
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)) or any(i not in self.engine.banks for i in ids):
            raise ValueError("drop_off.food_bank_ids must name known, distinct food banks")
        return {"window":{"start":window['start'],"end":window['end']},"refrigerated":raw.get('refrigerated',False),"capacity_lb":number(raw['capacity_lb']),"food_bank_ids":list(ids)}

    def usable_life(self, item, owner):
        """``usable_until`` and its basis for one offered item (ADR 0002, 0003).

        The donor's own condition check wins. Without one, a ``good`` item gets its produce
        profile's minimum usable days, labeled as a profile assumption. A ``use_soon`` item
        needs the donor's time: the profile has no use-soon life, and none is invented.
        """
        if item.get('usable_until'):
            dt(item['usable_until'])
            return item['usable_until'],{"kind":"donor_condition_check","organization_id":owner}
        if item['condition_grade']=='use_soon':
            raise ValueError("a use_soon item needs the donor's usable_until; the produce profile gives no use-soon life")
        profile=self.engine.calc.profiles.get(item['produce_id'])
        field='days_usable_cold' if profile.needs_cold else 'days_usable_room'
        days=getattr(profile,field)
        if days is None:
            raise ValueError(f"the {profile.name} profile gives no {field}; the donor's condition check must state usable_until")
        source=profile.provenance.get(field)
        basis={"kind":"profile_assumption","field":field,"days":days.min,"profile_set_version":profile.profile_set_version,
               "field_sources":list(source.sources) if source else [],"field_assumption":source.assumption if source else None,
               "note":"The profile's general minimum life, counted from the report time; not this lot's own condition. A condition check overrides it."}
        return (dt(self.engine.now)+timedelta(days=days.min)).isoformat(),basis

    def lot_item(self, lot, item):
        """One item of ``get_lot``: its split, unclaimed pounds once the lot is settled, and reach."""
        d,pid=lot['draft'],item['produce_id']
        movers={t['food_bank_id']:t['mover'] for t in d['transports']}
        split=[{"food_bank_id":a['food_bank_id'],"pounds":a['pounds'],"mover":movers.get(a['food_bank_id'])} for a in d['allocations'] if a['produce_id']==pid and a['pounds']>0]
        if lot.get('change_version'):
            # A committed change (a cooler failure) amended the commitments, not the draft: follow the commitments.
            # Produce a change moved goes by the proposing food bank's own truck, so it is a food bank mover.
            split=[{"food_bank_id":a['food_bank_id'],"pounds":a['pounds'],
                    "mover":'food_bank' if a.get('version')==lot['change_version'] and a.get('pathway') is None else movers.get(a['food_bank_id'])}
                   for a in lot['commitments'] if a['produce_id']==pid and a['pounds']>0]
        committed=sum(a['pounds'] for a in lot['commitments'] if a['produce_id']==pid)
        settled=lot['status'] in ('committed','unclaimed','preserved_disagreement')
        reached={p['request_code'] for p in self.records.all('pickup') if p['lot_id']==d['lot_id'] and p['status']=='collected' and any(x['produce_id']==pid for x in p['items'])}
        return {**item,"name":self.engine.calc.profiles.get(pid).name,"status":lot['status'],"split":split,
                "unclaimed_lb":max(0.0,item['pounds']-committed) if settled else 0,"households_reached":len(reached),
                "usable_until_basis":lot.get('usable_until_basis',{}).get(pid)}

    def release(self, pid, code):
        with self.records.transaction():
            p=self.records.get("pickup",pid)
            if p["request_code"]!=code:
                raise Unauthorized("pickup belongs to a different request")
            if p["status"]=="collected":
                raise Conflict("collected pickup cannot be released")
            if p["status"]!="released":
                p["status"]="released"
                self.records.put("pickup",pid,p)
                self.records.event(p["lot_id"],self.engine.now,"pickup_released",{"pickup_id":pid,"pounds":p["pounds"],"source":"household"})
                lot=self.records.get("lot",p["lot_id"])
                bank=self.records.get("bank",p["food_bank_id"])
                bank={**bank,'pickup_windows':[p['window']]}
                for item in p["items"]:
                    original=next(i for i in lot["draft"]["items"] if i["produce_id"]==item["produce_id"])
                    rs=[r for r in self.records.all("request") if r["request_code"]!=code and self.engine.eligible(r,bank,original,max(dt(self.engine.now),dt(p["window"]["start"]))) ]
                    portions=self.engine.calc.household_portions(item["pounds"],[{"request_code":r["request_code"],"household_size":r["household_size"],"received_lb":r.get("received_this_week_lb",0)+self.engine.reserved(r["request_code"])} for r in rs])
                    for part in portions["portions"]:
                        if part["pounds"]<=1e-8:
                            continue
                        r=next(r for r in rs if r["request_code"]==part["request_code"])
                        new_id=f"pk-{secrets.token_hex(8)}"
                        new={**p,"pickup_id":new_id,"request_code":r["request_code"],"pounds":part["pounds"],"items":[{**item,"pounds":part["pounds"]}],"window":self.engine.eligible(r,bank,original,max(dt(self.engine.now),dt(p["window"]["start"]))),"status":"committed"}
                        new.pop('moved_from_food_bank_id',None)
                        new.pop('reply_expected',None)
                        self.records.put("pickup",new_id,new)
                        self.records.event(p["lot_id"],self.engine.now,"pickup_notice",new)
            try:
                language=self.records.get("request",code).get("language","en")
            except KeyError:
                language="en"
            return {"pickup_id":pid,"status":"released","released":True,"released_lb":p["pounds"],"message":RELEASED_MESSAGE.get(language,RELEASED_MESSAGE["en"])}

    def dispatch(self,method,target,b,token):
        path=urlsplit(target).path.strip('/').split('/')
        q={k:v[0] for k,v in parse_qs(urlsplit(target).query).items()}
        root=path[0]
        calc=self.engine.calc
        if root=='approvals' and method=='POST' and ('event_id' in b or b.get('organization_id')=='donor'):
            # Compatibility with Lane C's existing capability-verified human relay.
            # The event denotes the same lot; normalize names, never the decision.
            b=copy.deepcopy(b)
            b['lot_id']=b.get('lot_id',b.get('event_id'))
            if b.get('organization_id')=='donor':
                b['organization_id']=self.records.get('lot',b['lot_id'])['draft']['donor_id']
            digest=b.get('terms_hash','')
            if len(digest)==64 and all(c in '0123456789abcdef' for c in digest):
                b['terms_hash']='sha256:'+digest
        if method=='GET' and path==['']:
            return 200,{"contract_version":CONTRACT_VERSION,"operations":[{"operation":o,"method":m,"path":p,"status":st} for o,m,p,st in OPERATIONS]}
        if method=='GET' and root=='health':
            if self.email_dispatcher_thread is not None and not self.email_dispatcher_thread.is_alive():
                return 503,{"error":{"code":"email_worker_unavailable","message":"Pickup email delivery is unavailable"}}
            return 200,{"status":"ok","contract_version":CONTRACT_VERSION}
        if method=='GET' and root=='fair-share':
            share=calc.fair_share(int(q.get('household_size',0)))
            return 200,{"household_size":share.household_size,"fair_share_lb":share.pounds,"period":share.period,"table_version":share.table_version,"is_placeholder":share.is_placeholder,"wording":desk.fair_share_wording(share.pounds,desk.Language(q.get('language','en')))}
        if method=='POST' and root=='voice-intake':
            if self.extractor is None:
                return 503,{"error":{"code":"voice_unavailable","message":"Use the text form; voice extraction is not configured"}}
            if not self.voice_allowed():
                return 503,{"error":{"code":"rate_limited","message":"Too many voice calls right now; try again shortly or use the text form"}}
            from harvestnet_agents.llm_negotiators import SpendingCapReached
            transcript=desk.Transcript.from_dict(b.get('transcript',b))
            try:
                draft=desk.intake_transcript(transcript,self.extractor)
            except SpendingCapReached:
                return 503,{"error":{"code":"spending_cap_reached","message":"Voice extraction has reached its spending cap; use the text form"}}
            except desk.ExtractionError:
                return 503,{"error":{"code":"voice_unavailable","message":"Voice extraction failed; use the text form"}}
            return 200,{"call_id":b.get('call_id'),**self.preview(draft),"next":"consent" if draft.is_complete else "ask_missing_questions"}
        if root=='requests' and method=='POST' and (len(path)==1 or path[1]=='preview'):
            if any(k in b for k in ('name','address','income')):
                raise ValueError("names, addresses and income are not collected")
            if 'phone' in b:
                # contract-v0.2: pickup messages go by email, not SMS (user decision, October 11, 2026).
                raise ValueError("phone numbers are no longer collected; give an optional email for pickup messages")
            draft=desk.draft_from_form(b,desk.Language(b.get('language','en')))
            if len(path)>1:
                return 200,self.preview(draft)
            if not draft.is_complete or b.get('consent') is not True:
                raise ValueError("complete answers and explicit consent are required")
            if b.get('channel','web') not in ('web','voice'):
                raise ValueError("channel must be web or voice")
            share=calc.fair_share(draft.household_size)
            # Optional, write-only, for pickup emails only. Checked before anything is saved.
            email=email_address(b['email']) if b.get('email') not in (None,'') else None
            with self.records.transaction():
                code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
                try:
                    self.records.get('request',code)
                except KeyError:
                    pass
                else:
                    raise Conflict("request code collision; retry")
                r={**draft.to_dict(),"request_code":code,"fair_share_lb":share.pounds,"table_version":share.table_version,"received_this_week_lb":0,"initial_received_lb":0,"chosen_food_bank_ids":[],"expires_at":(dt(self.engine.now)+timedelta(days=7)).isoformat(),"submitted_at":self.engine.now,"channel":b.get('channel','web'),"consent":True}
                self.records.put('request',code,r)
                if email:
                    self.records.put('email',code,{"email":email,"expires_at":r['expires_at']})
            return 201,{k:r[k] for k in ('request_code','household_size','fair_share_lb','received_this_week_lb','table_version','chosen_food_bank_ids','expires_at')} | {"emails":email is not None,"next":"choose_food_banks"}
        if root=='requests' and len(path)>=2:
            r=self.records.get('request',path[1])
            if method=='PUT' and path[2:]==['food-banks']:
                ids=b['food_bank_ids'] if 'food_bank_ids' in b else b['chosen_food_bank_ids']
                if not isinstance(ids,list) or len(ids)!=len(set(ids)) or any(i not in self.engine.banks for i in ids):
                    raise ValueError("choose known, distinct food banks")
                with self.records.transaction():
                    r['chosen_food_bank_ids']=ids
                    self.records.put('request',path[1],r)
                return 200,{"request_code":path[1],"chosen_food_bank_ids":ids,"status":"saved","message":SAVED_MESSAGE.get(r.get('language'),SAVED_MESSAGE['en'])}
            if method=='GET' and len(path)==2:
                # The page's language when it sends one, else the language the household chose.
                language=desk.Language(q.get('language') or r['language']).value
                pickups=[{k:v for k,v in p.items() if k!='request_code'} | {"items":[{**i,"name":self.item_name(i["produce_id"],language)} for i in p["items"]],"wording":self.wording(p,r,language)} for p in self.records.all('pickup') if p['request_code']==path[1] and p['status']=='committed']
                return 200,{k:r[k] for k in ('request_code','household_size','fair_share_lb','received_this_week_lb','chosen_food_bank_ids','expires_at')} | {"pickups":pickups,"market_match_tip":None}
        if root=='pickups' and method=='POST' and len(path)==3 and path[2]=='release':
            return 200,self.release(path[1],b['request_code'])
        if root=='pickup-confirmations' and method=='POST':
            owner=b['food_bank_id']
            self.authorize(owner,token)
            r=self.records.get('request',b['request_code'])
            pending=[p for p in self.records.all('pickup') if p['request_code']==b['request_code'] and p['food_bank_id']==owner and p['status']=='committed']
            if not pending:
                raise Conflict("no open pickup at this food bank")
            if any(not (dt(p['window']['start'])<=dt(self.engine.now)<dt(p['window']['end'])) for p in pending):
                raise Conflict("pickup is outside its confirmed window")
            with self.records.transaction():
                for p in pending:
                    p['status']='collected'
                    self.records.put('pickup',p['pickup_id'],p)
                    self.records.event(p['lot_id'],self.engine.now,'pickup_confirmation',{"pickup_id":p['pickup_id'],"pounds":p['pounds']})
                collected=sum(p['pounds'] for p in pending)
                r['received_this_week_lb']+=collected
                self.records.put('request',r['request_code'],r)
            return 200,{"pickup_id":pending[0]['pickup_id'],"request_code":r['request_code'],"food_bank_id":owner,"status":"collected","collected_lb":collected,"received_this_week_lb":r['received_this_week_lb'],"fair_share_lb":r['fair_share_lb'],"confirmed_at":self.engine.now,"items":[i for p in pending for i in p['items']]}
        if root=='produce-profiles' and method=='GET':
            profiles=list(calc.profiles.profiles.values())
            return 200,{"profile_set_version":calc.profiles.version,"profiles":[{"produce_id":p.id,"name":p.name,"units":list(p.units),"needs_fridge":p.needs_fridge,"needs_cold":p.needs_cold} for p in profiles],"units_needing_pack_weight":{p.id:[u for u,w in p.units.items() if w is None] for p in profiles}}
        if root=='surplus-offers' and method=='POST':
            owner=b['donor_id']
            self.authorize(owner,token)
            if owner not in self.engine.donors:
                raise ValueError("unknown donor")
            offer=copy.deepcopy(b)
            offer['lot_id']='lot-'+secrets.token_hex(8)
            offer['reported_at']=self.engine.now
            if dt(offer['deadline'])<=dt(self.engine.now):
                raise ValueError("deadline already passed")
            if not isinstance(offer['items'],list) or not offer['items'] or not all(isinstance(i,dict) for i in offer['items']):
                raise ValueError("an offer needs a list of items")
            basis={}
            for i in offer['items']:
                if i.get('produce_id') not in calc.profiles:
                    raise ValueError(f"unknown produce_id {i.get('produce_id')!r}; GET /produce-profiles lists them")
                if i['condition_grade'] not in ('good','use_soon','not_for_people'):
                    raise ValueError("condition_grade must be good, use_soon or not_for_people")
                i['usable_until'],basis[i['produce_id']]=self.usable_life(i,owner)
            offer['usable_until_basis']=basis
            if 'drop_off' in b:
                # This offer's drop-off only; the donor's recorded drop-off stays as it is.
                offer['drop_off']=self.drop_off(b['drop_off'])
            draft=self.engine.create_offer(offer)
            from .workflows import negotiate_pending
            negotiate_pending(self.engine,offer['lot_id'])
            return 201,{"lot_id":offer['lot_id'],"version":1,"status":"offered","items":[{"produce_id":i['produce_id'],"name":calc.profiles.get(i['produce_id']).name,"pounds":i['pounds'],"usable_until":i['usable_until'],"usable_until_basis":basis[i['produce_id']]} for i in draft['items']],"needs_human":[i['produce_id'] for i in draft['items'] if i.get('condition_doubt')],"message":"Nothing is promised until every named organization approves."}
        if root=='lots' and len(path)>=2:
            lot=self.records.get('lot',path[1]); d=lot['draft']
            if method=='GET' and len(path)==2:
                return 200,{"lot_id":path[1],"donor_id":d['donor_id'],"status":lot['status'],"current_version":d['version'],"deadline":d['deadline'],"items":[self.lot_item(lot,i) for i in d['items']],"draft":d,"approvals":list(lot['approvals'].values()),"awaiting_approval_from":[o for o in named(d) if lot['approvals'].get(o,{}).get('decision')!='approve'],"disagreement":lot.get('stop_reason')}
            if method=='GET' and path[2:]==['versions']:
                return 200,{"lot_id":path[1],"versions":[{"version":v['version'],"proposer_id":v['proposer_id'],"move":"counter" if v['version']>1 else "offer","reason":v['reason'],"change":next((e['data']['amendment'] for e in self.records.events(path[1]) if e['kind']=='amendment' and e['data']['draft']['version']==v['version']),None)} for v in lot['versions']],"current_version":d['version']}
            if method=='POST' and path[2:]==['counters']:
                self.authorize(b['organization_id'],token)
                if b['version']!=d['version'] or lot['status']=='committed':
                    raise Conflict("stale or committed version")
                from harvestnet_agents.negotiation import amendment_from_dict,parse_draft
                parse_draft(d).amend(amendment_from_dict(b['amendment']),proposer_id=b['organization_id'],reason=b['reason'])
                move={"organization_id":b['organization_id'],"version":b['version'],"action":"counter","amendment":b['amendment'],"reason":b['reason']}
                with self.records.transaction():
                    self.records.put('queued_move',path[1]+':'+b['organization_id'],{"lot_id":path[1],**move})
                from .workflows import negotiate_pending
                negotiate_pending(self.engine,path[1])
                return 202,{"lot_id":path[1],"status":"queued_for_turn","based_on_version":d['version'],"move":move,"message":"Counter queued for your organization's next turn."}
            if method=='POST' and path[2:]==['condition-checks']:
                self.authorize(b['organization_id'],token)
                updated=self.engine.protocol.condition_check(path[1],b['version'],b['organization_id'],b['produce_id'],b['condition_grade'],b['usable_until'],b['reason'],self.engine.now)
                from .workflows import negotiate_pending
                negotiate_pending(self.engine,path[1])
                return 200,{'lot_id':path[1],'version':updated['version'],'status':'condition_recorded','committed':False}
            # Proposed (#23): a food bank's holding and its changed version after a disruption.
            if method=='GET' and path[2:]==['holding']:
                self.authorize(q.get('food_bank_id'),token)
                return 200,changes.holding(self.engine,path[1],q['food_bank_id'])
            if method=='POST' and path[2:]==['changes']:
                owner=(b.get('terms') or {}).get('proposer_id')
                self.authorize(owner,token)
                return 201,changes.propose(self.engine,path[1],b,owner)
        if root=='approvals':
            owner=b.get('organization_id') if method=='POST' else q.get('organization_id')
            self.authorize(owner,token)
            if method=='GET':
                approvals=[]
                for lot in self.records.all('lot'):
                    d=lot['draft']
                    if owner in named(d) and lot['status']!='committed' and dt(d['deadline'])>dt(self.engine.now):
                        approvals.append({"lot_id":d['lot_id'],"version":d['version'],"terms_hash":terms_hash(d),"requested_at":self.engine.now,"expires_at":d['deadline'],"why_you":["exact_version_review"],"summary":d['reason'],"terms":d,"status":"awaiting_decision"})
                approvals+=changes.pending_approvals(self.records,owner)
                return 200,{"organization_id":owner,"approvals":approvals}
            if method=='POST':
                receipt={k:b[k] for k in ('lot_id','version','organization_id','terms_hash','decision')}
                if b.get('receipt_id'): receipt['receipt_id']=b['receipt_id']
                if changes.find(self.records,receipt['lot_id'],receipt['version']):
                    # A changed version of a committed plan takes its own fresh approvals.
                    result=changes.approve(self.engine,receipt,owner)
                    return 200,{**receipt,"receipt_id":b.get('receipt_id'),"status":"approval_recorded","change_status":result['status'],"committed":result['committed'],"approved_by":result['approved_by'],"awaiting_approval_from":result['waiting_for']}
                # A committed change supersedes the version it changed. The lot's own draft stays at
                # that earlier version, so a decision on it would otherwise still be accepted.
                if type(receipt['version']) is int:
                    newer=[c['version'] for c in changes.changes_for(self.records,receipt['lot_id']) if c['status']=='committed' and c['version']>receipt['version']]
                    if newer:
                        raise Conflict(f"version {receipt['version']} was superseded by committed version {max(newer)}; decide on the current version")
                result=self.engine.protocol.approve(receipt,owner,self.engine.now,self.engine.validate)
                self.engine.distribute(b['lot_id'])
                return 200,{**receipt,"receipt_id":b.get('receipt_id'),"status":"approval_recorded","committed":result['committed'],"approved_by":result['approved_by'],"awaiting_approval_from":result['waiting_for']}
        if root=='food-banks':
            if len(path)==1 and method=='GET':
                banks=[]
                request=self.records.get('request',q['request_code']) if q.get('request_code') else None
                language=desk.Language(q.get('language') or (request or {}).get('language') or 'en').value
                for bid in self.engine.banks:
                    bank=self.records.get('bank',bid)
                    committed=[{"produce_id":a['produce_id'],"name":self.item_name(a['produce_id'],language),"pounds":a['pounds'],"badges":["keep_cold"] if calc.profiles.get(a['produce_id']).needs_cold else []} for lot in self.records.all('lot') if lot['status']=='committed' for a in lot['commitments'] if a['food_bank_id']==bid]
                    fits=None
                    if request:
                        probe={"produce_id":"apples","usable_until":request['expires_at']}
                        candidate={**request,"chosen_food_bank_ids":[bid]}
                        fits=bool(self.engine.eligible(candidate,bank,probe,dt(self.engine.now)))
                    banks.append({"food_bank_id":bid,"name":self.engine.names[bid],"area":bank['area'],"pickup_windows":bank['pickup_windows'],"fits_your_pickup_times":fits,"committed_now":committed})
                return 200,{"food_banks":banks}
            if len(path)==3:
                bid=path[1]; self.authorize(bid,token)
                bank=self.records.get('bank',bid)
                if path[2]=='status' and method=='PUT':
                    from harvestnet_agents.negotiation import parse_facts
                    updated={**bank,**{k:b[k] for k in ('storage','pickup_windows','truck','cooler') if k in b}}
                    parse_facts('food_bank',{"food_bank_id":bid,"name":self.engine.names[bid],"demand":self.engine.demand(bid),**updated})
                    for s in updated['storage']: number(s['cold_free_lb']); number(s['dry_free_lb'])
                    updated['status_version']=bank.get('status_version',0)+1
                    with self.records.transaction(): self.records.put('bank',bid,updated)
                    return 200,{"food_bank_id":bid,"status_version":updated['status_version'],"updated_at":self.engine.now,"message":"Your organization's facts are updated."}
                if path[2]=='dashboard' and method=='GET':
                    incoming=[]
                    arrivals=[]
                    disagreements=[]
                    for lot in self.records.all('lot'):
                        d=lot['draft']; allocations=[a for a in d['allocations'] if a['food_bank_id']==bid]
                        if not allocations: continue
                        transport=next((t for t in d['transports'] if t['food_bank_id']==bid),None)
                        incoming.append({"lot_id":d['lot_id'],"version":d['version'],"donor_id":d['donor_id'],"donor_name":self.engine.names[d['donor_id']],"for_us":[{"produce_id":a['produce_id'],"name":calc.profiles.get(a['produce_id']).name,"pounds":a['pounds']} for a in allocations],"transport":transport,"agent_suggests":None,"agent_reason":d['reason'],"needs_your_approval":lot['status']!='committed'})
                        if transport: arrivals.append({"lot_id":d['lot_id'],"version":d['version'],"arrives_at":transport['arrives_at'],"items":allocations,"status":lot['status']})
                        if lot.get('stop_reason'): disagreements.append({"lot_id":d['lot_id'],"reason":lot['stop_reason']})
                    return 200,{"food_bank_id":bid,"name":self.engine.names[bid],"capacity":{k:bank.get(k) for k in ('storage','pickup_windows','truck','cooler')},"incoming_offers":incoming,"fair_share_gap":self.engine.demand(bid),"disagreements":disagreements,"expected_arrivals":arrivals,"disruptions":changes.summaries(self.records,bid)}
        if root=='results' and method=='GET':
            try:
                return 200,self.records.get('results',q['scenario_id'])
            except NotFound:
                return 404,{"error":{"code":"not_found","message":"No evaluation published for this scenario; run python -m harvestnet_core evaluate"}}
        return 404,{"error":{"code":"not_found","message":"Unknown operation"}}
