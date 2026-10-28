"""Real record-backed operations at the agreed public API paths."""
from collections import deque
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import secrets
import time
from urllib.parse import urlsplit, parse_qs
from harvestnet_agents import front_desk as desk
from harvestnet_agents.negotiation import MoveKind, parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from .engine import Engine
from . import changes
from harvestnet_agents.terms import terms_hash
from .protocol import Conflict, dt, named, number
from .records import NotFound
from .contact import email_address
from .workflows import negotiate_pending


class Unauthorized(ValueError):
    pass


class MissingField(ValueError, KeyError):
    """A field the caller's body or query left out: bad input (400), unlike a missing record key."""

    def __str__(self):
        return f"missing field {self.args[0]!r}"


class Body(dict):
    """The caller's JSON. Only a missing field here is the caller's error; a ``KeyError`` from
    anywhere else is a server bug and answers 500."""

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            raise MissingField(key) from None


def caller_input(value):
    """JSON from the caller, with every object a ``Body``."""
    if isinstance(value, dict):
        return Body({k: caller_input(v) for k, v in value.items()})
    if isinstance(value, list):
        return [caller_input(v) for v in value]
    return value


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

log = logging.getLogger(__name__)

# The longest a read waits before purge runs again, for records another API process added.
PURGE_INTERVAL = timedelta(minutes=1)

# Voice intake calls per process in a sliding window (#22). Each call can cost a model call.
VOICE_RATE_LIMIT = (20, 60.0)

# What a household sees after "Can't make it", in its own language (ticket #6).
RELEASED_MESSAGE = {
    'en': "Thanks for telling us. Your portion will go to another family.",
    'es': "Gracias por avisarnos. Su porción pasará a otra familia.",
}
# Why the dashboard has no suggestion for an offer that is no longer open.
NO_SUGGESTION = {
    'committed': "This offer is already committed; there is nothing left to decide.",
    'unclaimed': "The deadline passed and the produce is unclaimed; no decision is open.",
    'preserved_disagreement': "The organizations kept their disagreement; nothing is open for approval.",
}
# What the food bank's own negotiator did, as the dashboard's buttons name it.
SUGGESTED = {MoveKind.ACCEPT: 'accept', MoveKind.REQUEST_HOLD: 'accept', MoveKind.COUNTER: 'counter',
             MoveKind.REJECT: 'decline', MoveKind.ASK_HUMAN: 'ask_human'}
SAVED_MESSAGE = {
    'en': "Your food banks are saved.",
    'es': "Sus bancos de alimentos están guardados.",
}


@dataclass(frozen=True)
class Call:
    """One request to an operation: path parameters, query, JSON body and the bearer token."""
    params: dict
    query: dict
    body: dict
    token: str | None


def match_route(template, segments):
    """The ``{name}`` values of ``template`` if ``segments`` fit it, else ``None``."""
    pattern=template.strip('/').split('/')
    if len(pattern)!=len(segments):
        return None
    params={}
    for want,got in zip(pattern,segments):
        if want.startswith('{') and want.endswith('}'):
            params[want[1:-1]]=got
        elif want!=got:
            return None
    return params


class API:
    def __init__(self, engine, *, clock=None, staff_tokens=None, extractor=None, voice_rate_limit=VOICE_RATE_LIMIT, monotonic=time.monotonic,
                 household_page_url=None, approvals_token=None):
        self.engine=engine
        self.records=engine.records
        self.clock=clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.tokens=staff_tokens or {}
        if len(set(self.tokens.values())) != len(self.tokens) or any(not v for v in self.tokens.values()):
            raise ValueError("each organization needs its own nonempty token")
        # Proposed (platform isolation): the approval bridge's own credential. It records one
        # human's decision from a review link and nothing else; it is never a staff token.
        if approvals_token is not None and (not isinstance(approvals_token, str) or len(approvals_token) < 16
                                            or approvals_token in self.tokens.values()):
            raise ValueError("the approvals credential must be its own secret of at least 16 characters")
        self.approvals_token=approvals_token
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
        self.next_purge=None
        if household_page_url:
            self.records.enable_email_outbox()

    def authorize(self, owner, token):
        expected=self.tokens.get(owner)
        if not expected or not secrets.compare_digest(token or "",expected):
            raise Unauthorized("organization staff authentication required")

    def authorize_decision(self, owner, token, body):
        """Record a human decision: the organization's own staff token, or the approval bridge's
        scoped credential for one review-link decision. The scoped credential is accepted nowhere
        else, needs the link's receipt ID, and still goes through every version, terms-hash,
        named-organization and deadline check in protocol.approve / changes.approve."""
        if self.approvals_token and secrets.compare_digest(token or "", self.approvals_token):
            rid=body.get('receipt_id')
            if not isinstance(rid,str) or not 16<=len(rid)<=64 or owner not in self.tokens:
                raise Unauthorized("the approvals credential records only a review link's decision, with its receipt ID")
            return
        self.authorize(owner,token)

    def purge(self):
        with self.records.transaction():
            for lot in self.records.all('lot'):
                # A preserved disagreement is a result, not an open lot: it survives the deadline
                # with its options and reasons (design section 8). Only a lot still being negotiated
                # or awaiting approvals becomes unclaimed.
                if lot['status'] not in ('committed','unclaimed','preserved_disagreement') and dt(lot['draft']['deadline'])<=dt(self.engine.now):
                    lot.update(status='unclaimed',holds={},stop_reason='Deadline passed without every exact-version approval; nothing auto-committed')
                    self.records.put('lot',lot['draft']['lot_id'],lot)
                    self.records.event(lot['draft']['lot_id'],self.engine.now,'deadline_unclaimed',{'reason':lot['stop_reason']})
        reopened=[lot['draft']['lot_id'] for lot in self.records.all('lot') if lot['status']=='awaiting_approvals' and self.engine.protocol.expire_holds(lot['draft']['lot_id'],self.engine.now)]
        for lot_id in reopened:
            negotiate_pending(self.engine,lot_id)
        with self.records.transaction():
            for r in self.records.all("request"):
                if dt(r["expires_at"])>dt(self.engine.now):
                    continue
                code=r["request_code"]
                self.records.delete("request",code)
                self.records.delete("email",code)
                self.records.delete("phone",code)  # retired with contract-v0.2; kept so old records still go
                # Design section 12: results keep only counts. A collected pickup stays as a count
                # (pounds, items, food bank, lot) under a fresh random household reference, so
                # households reached and collected pounds do not shrink later; its request code and
                # window go. Every other pickup of the request is deleted, as before.
                household="expired-"+secrets.token_hex(8)
                for p in self.records.all("pickup"):
                    if p["request_code"]!=code:
                        continue
                    if p["status"]=="collected":
                        self.records.put("pickup",p["pickup_id"],{**p,"request_code":household,"window":None,"anonymized":"request expired"})
                    else:
                        self.records.delete("pickup",p["pickup_id"])
                # Pickup notices keep the pounds and food bank; the request code and household window go.
                for e in self.records.events_of_kind("pickup_notice"):
                    if e["data"].get("request_code")==code:
                        self.records.replace_event_data(e["sequence"],{**e["data"],"request_code":None,"window":None,"anonymized":"request expired"})
        self.next_purge=self.purge_due()

    def purge_due(self):
        """When purge next has work: the earliest open lot's deadline, hold end of a lot awaiting
        approvals, or request expiry. Never later than ``PURGE_INTERVAL`` from now, since another
        API process may add records this one has not seen."""
        due=[dt(self.engine.now)+PURGE_INTERVAL]
        for lot in self.records.all('lot'):
            if lot['status'] not in ('committed','unclaimed','preserved_disagreement'):
                due.append(dt(lot['draft']['deadline']))
            if lot['status']=='awaiting_approvals':
                due+=[dt(h['end']) for hs in lot['holds'].values() for h in hs]
        due+=[dt(r['expires_at']) for r in self.records.all('request')]
        return min(due)

    def call(self, method, target, body=None, token=None):
        # Reads and mutations share one lock; never leak database exception contents.
        with self.records.lock:
            self.engine.now=self.clock()
            # Every change runs purge; a read runs it only when something is due (or the interval
            # passed), so reads do not rescan and rewrite every record.
            if method!='GET' or self.next_purge is None or dt(self.engine.now)>=self.next_purge:
                self.purge()
            try:
                status,data=self.dispatch(method,target,caller_input(body or {}),token)
                return status,{"mode":self.engine.fixture["mode"],"synthetic":self.engine.fixture["synthetic"],**data}
            except Unauthorized as exc:
                return 401,{"error":{"code":"unauthorized","message":str(exc)}}
            except NotFound:
                return 404,{"error":{"code":"not_found","message":"Record not found"}}
            except Conflict as exc:
                return 409,{"error":{"code":"conflict","message":str(exc)}}
            except ValueError as exc:
                # Validation: a missing field (MissingField) or a value the rules refuse.
                return 400,{"error":{"code":"bad_request","message":str(exc)}}
            except Exception:
                # Anything else is a server bug: logged here, never shown to the caller.
                log.exception("unexpected error in %s /%s", method, urlsplit(target).path.strip('/').split('/')[0])
                return 500,{"error":{"code":"internal_error","message":"Something went wrong on our side"}}

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

    def wording(self,pickup,request,language=None):
        language=desk.Language(language or request["language"])
        window=pickup["window"]
        portions=[desk.ProducePortion(self.item_name(item["produce_id"],language.value).lower(),item["pounds"],"committed") for item in pickup["items"]]
        facts=desk.PickupFacts(pickup["food_bank_name"],dt(window["start"]).time(),dt(window["end"]).time(),request["request_code"],portions,request.get("received_this_week_lb",0),request["fair_share_lb"])
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
        draft,pid=lot['draft'],item['produce_id']
        movers={t['food_bank_id']:t['mover'] for t in draft['transports']}
        split=[{"food_bank_id":a['food_bank_id'],"pounds":a['pounds'],"mover":movers.get(a['food_bank_id'])} for a in draft['allocations'] if a['produce_id']==pid and a['pounds']>0]
        if lot.get('change_version'):
            # A committed change (a cooler failure) amended the commitments, not the draft: follow the commitments.
            # Produce a change moved goes by the proposing food bank's own truck, so it is a food bank mover.
            split=[{"food_bank_id":a['food_bank_id'],"pounds":a['pounds'],
                    "mover":'food_bank' if a.get('version')==lot['change_version'] and a.get('pathway') is None else movers.get(a['food_bank_id'])}
                   for a in lot['commitments'] if a['produce_id']==pid and a['pounds']>0]
        committed=sum(a['pounds'] for a in lot['commitments'] if a['produce_id']==pid)
        settled=lot['status'] in ('committed','unclaimed','preserved_disagreement')
        reached={pickup['request_code'] for pickup in self.records.all('pickup') if pickup['lot_id']==draft['lot_id'] and pickup['status']=='collected' and any(entry['produce_id']==pid for entry in pickup['items'])}
        unclaimed=max(0.0,item['pounds']-committed) if settled else 0
        reason={"unclaimed_reason":lot.get('stop_reason') or "No food bank took these pounds in the approved plan"} if unclaimed>1e-8 else {}
        return {**item,"name":self.engine.calc.profiles.get(pid).name,"status":self.item_status(lot,pid),"split":split,
                "unclaimed_lb":unclaimed,**reason,"households_reached":len(reached),
                "usable_until_basis":lot.get('usable_until_basis',{}).get(pid)}

    def item_status(self, lot, pid):
        """One item's own status (contract get_lot): offered, negotiating, held, committed, moving,
        at_food_bank, collected, disagreement or unclaimed. Derived from the lot's records: its
        holds, its commitments, its transports (or a committed change's trip) against the
        clock, and its pickups. The lot's status is not copied."""
        d,status=lot['draft'],lot['status']
        if status=='unclaimed':
            return 'unclaimed'
        if status=='preserved_disagreement':
            return 'disagreement'
        if status=='committed':
            committed=[a for a in lot['commitments'] if a['produce_id']==pid and a['pounds']>0]
            return self.item_progress(lot,pid,committed) if committed else 'unclaimed'
        planned=[a for a in d['allocations'] if a['produce_id']==pid and a['pounds']>0]
        if not planned:
            return 'offered' if d['version']==1 else 'negotiating'
        owners={d['donor_id']}|{a['food_bank_id'] for a in planned}
        return 'held' if all(lot['holds'].get(o) for o in owners) else 'negotiating'

    def item_progress(self, lot, pid, committed):
        """A committed item: collected once every live pickup of it was, else by how far its trips have got."""
        lot_id=lot['draft']['lot_id']
        live=[p for p in self.records.all('pickup') if p['lot_id']==lot_id and p['status']!='released' and any(i['produce_id']==pid for i in p['items'])]
        if live and all(p['status']=='collected' for p in live):
            return 'collected'
        now=dt(self.engine.now)
        trips=[]
        for a in committed:
            trip=changes.trip(self.records,lot,a)
            if trip:
                trips.append(trip)
        if trips and all(now>=arrives for _,arrives in trips):
            return 'at_food_bank'
        if any(now>=departs for departs,_ in trips):
            return 'moving'
        return 'committed'

    def suggestion(self, lot, bank_id):
        """The suggested move and its reason for one offer, from this food bank's own rules-based
        negotiator and its own facts only (ADR 0001). A fresh negotiator answers, so asking never
        changes what the real negotiation remembers. ``(None, reason)`` when none applies."""
        d=lot['draft']
        if lot['status'] not in ('awaiting_approvals','negotiating'):
            return None,NO_SUGGESTION.get(lot['status'],d['reason'])
        try:
            _,typed=parse_agent_input({'role':'food_bank','draft':d,'facts':self.engine.facts(bank_id,d),
                                       'turn':{'organization_id':bank_id,'number':1,'now':self.engine.now,'accepted_by':[]}})
            move=rules_negotiator('food_bank',bank_id,self.engine.calc).move(typed)
        except (ValueError,KeyError) as exc:
            return None,f"No suggestion yet: your negotiator could not review this version ({exc})"
        return SUGGESTED.get(move.kind),move.reason

    def disagreement_view(self, lot):
        """A preserved disagreement as the involved dashboards show it (design section 8): why the
        rounds stopped, the plans that were on the table, and each organization's last reason.
        Any other lot's stop reason is returned as before."""
        reason=lot.get('stop_reason')
        if lot['status']!='preserved_disagreement':
            return reason
        last={}
        for e in self.records.events(lot['draft']['lot_id']):
            if e['kind']=='move':
                last[e['data']['organization_id']]=e['data']
        options,seen=[],set()
        for v in reversed(lot['versions']):
            plan=[{"produce_id":a['produce_id'],"food_bank_id":a['food_bank_id'],"pounds":a['pounds']} for a in v['allocations'] if a['pounds']>0]
            key=repr(plan)
            if key in seen or len(options)>=3:
                continue
            seen.add(key)
            options.append({"version":v['version'],"proposer_id":v['proposer_id'],"reason":v['reason'],"allocations":plan})
        return {"reason":reason,"options":options,"reasons":[{"organization_id":o,"version":m['version'],"action":m['action'],"reason":m['reason']} for o,m in last.items()]}

    def awaiting_decision(self, lot, owner):
        """Whether ``owner`` has an open approval request on this lot: its current version awaits
        approvals, names ``owner``, has no decision from ``owner`` yet, and its deadline is ahead."""
        d=lot['draft']
        return lot['status']=='awaiting_approvals' and owner in named(d) and owner not in lot['approvals'] and dt(d['deadline'])>dt(self.engine.now)

    def requested_at(self, lot):
        """When the current version went out for approval: the last owner hold on that version."""
        version=lot['draft']['version']
        return max((e['at'] for e in self.records.events(lot['draft']['lot_id']) if e['kind']=='owner_hold' and e['data'].get('version')==version),
                   key=dt,default=None)

    def release(self, pid, code):
        with self.records.transaction():
            pickup=self.records.get("pickup",pid)
            if pickup["request_code"]!=code:
                raise Unauthorized("pickup belongs to a different request")
            if pickup["status"]=="collected":
                raise Conflict("collected pickup cannot be released")
            if pickup["status"]!="released":
                pickup["status"]="released"
                self.records.put("pickup",pid,pickup)
                self.records.event(pickup["lot_id"],self.engine.now,"pickup_released",{"pickup_id":pid,"pounds":pickup["pounds"],"source":"household"})
                lot=self.records.get("lot",pickup["lot_id"])
                bank=self.records.get("bank",pickup["food_bank_id"])
                bank={**bank,'pickup_windows':[pickup['window']]}
                for item in pickup["items"]:
                    original=next(offered for offered in lot["draft"]["items"] if offered["produce_id"]==item["produce_id"])
                    eligible=[request for request in self.records.all("request") if request["request_code"]!=code and self.engine.eligible(request,bank,original,max(dt(self.engine.now),dt(pickup["window"]["start"]))) ]
                    portions=self.engine.calc.household_portions(item["pounds"],[{"request_code":request["request_code"],"household_size":request["household_size"],"received_lb":request.get("received_this_week_lb",0)+self.engine.reserved(request["request_code"])} for request in eligible])
                    for part in portions["portions"]:
                        if part["pounds"]<=1e-8:
                            continue
                        household=next(request for request in eligible if request["request_code"]==part["request_code"])
                        new_id=f"pk-{secrets.token_hex(8)}"
                        new={**pickup,"pickup_id":new_id,"request_code":household["request_code"],"pounds":part["pounds"],"items":[{**item,"pounds":part["pounds"]}],"window":self.engine.eligible(household,bank,original,max(dt(self.engine.now),dt(pickup["window"]["start"]))),"status":"committed"}
                        new.pop('moved_from_food_bank_id',None)
                        new.pop('reply_expected',None)
                        self.records.put("pickup",new_id,new)
                        self.records.event(pickup["lot_id"],self.engine.now,"pickup_notice",new)
            try:
                language=self.records.get("request",code).get("language","en")
            except KeyError:
                language="en"
            return {"pickup_id":pid,"status":"released","released":True,"released_lb":pickup["pounds"],"message":RELEASED_MESSAGE.get(language,RELEASED_MESSAGE["en"])}

    # --- Routing: one named handler per operation ------------------------------------------

    def dispatch(self, method, target, body, token):
        """Run the handler of the operation that owns this method and path (``OPERATIONS`` is the
        route table, ``op_<operation>`` the handler). Anything else is a 404."""
        url=urlsplit(target)
        segments=url.path.strip('/').split('/')
        query=Body({name:values[0] for name,values in parse_qs(url.query).items()})
        if method=='GET' and segments==['']:
            return self.op_index()
        for operation,route_method,template,_ in OPERATIONS:
            params=match_route(template,segments) if route_method==method else None
            if params is not None:
                return getattr(self,'op_'+operation)(Call(params,query,body,token))
        return 404,{"error":{"code":"not_found","message":"Unknown operation"}}

    def op_index(self):
        return 200,{"contract_version":CONTRACT_VERSION,"operations":[{"operation":operation,"method":method,"path":path,"status":status} for operation,method,path,status in OPERATIONS]}

    def op_get_health(self, call):
        if self.email_dispatcher_thread is not None and not self.email_dispatcher_thread.is_alive():
            return 503,{"error":{"code":"email_worker_unavailable","message":"Pickup email delivery is unavailable"}}
        return 200,{"status":"ok","contract_version":CONTRACT_VERSION}

    # Households

    def op_get_fair_share(self, call):
        share=self.engine.calc.fair_share(int(call.query.get('household_size',0)))
        return 200,{"household_size":share.household_size,"fair_share_lb":share.pounds,"period":share.period,"table_version":share.table_version,"is_placeholder":share.is_placeholder,"wording":desk.fair_share_wording(share.pounds,desk.Language(call.query.get('language','en')))}

    def household_draft(self, body):
        """The household's answers as a draft request, refusing what is never collected."""
        if any(field in body for field in ('name','address','income')):
            raise ValueError("names, addresses and income are not collected")
        if 'phone' in body:
            # contract-v0.2: pickup messages go by email, not SMS (user decision, October 11, 2026).
            raise ValueError("phone numbers are no longer collected; give an optional email for pickup messages")
        return desk.draft_from_form(body,desk.Language(body.get('language','en')))

    def op_preview_request(self, call):
        return 200,self.preview(self.household_draft(call.body))

    def op_create_request(self, call):
        body=call.body
        draft=self.household_draft(body)
        if not draft.is_complete or body.get('consent') is not True:
            raise ValueError("complete answers and explicit consent are required")
        if body.get('channel','web') not in ('web','voice'):
            raise ValueError("channel must be web or voice")
        share=self.engine.calc.fair_share(draft.household_size)
        # Optional, write-only, for pickup emails only. Checked before anything is saved.
        email=email_address(body['email']) if body.get('email') not in (None,'') else None
        with self.records.transaction():
            code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
            try:
                self.records.get('request',code)
            except KeyError:
                pass
            else:
                raise Conflict("request code collision; retry")
            request={**draft.to_dict(),"request_code":code,"fair_share_lb":share.pounds,"table_version":share.table_version,"received_this_week_lb":0,"initial_received_lb":0,"chosen_food_bank_ids":[],"expires_at":(dt(self.engine.now)+timedelta(days=7)).isoformat(),"submitted_at":self.engine.now,"channel":body.get('channel','web'),"consent":True}
            self.records.put('request',code,request)
            if email:
                self.records.put('email',code,{"email":email,"expires_at":request['expires_at']})
        return 201,{field:request[field] for field in ('request_code','household_size','fair_share_lb','received_this_week_lb','table_version','chosen_food_bank_ids','expires_at')} | {"emails":email is not None,"next":"choose_food_banks"}

    def op_list_food_banks(self, call):
        query,calc=call.query,self.engine.calc
        request=self.records.get('request',query['request_code']) if query.get('request_code') else None
        language=desk.Language(query.get('language') or (request or {}).get('language') or 'en').value
        banks=[]
        for bank_id in self.engine.banks:
            bank=self.records.get('bank',bank_id)
            committed=[{"produce_id":a['produce_id'],"name":self.item_name(a['produce_id'],language),"pounds":a['pounds'],"badges":["keep_cold"] if calc.profiles.get(a['produce_id']).needs_cold else []} for lot in self.records.all('lot') if lot['status']=='committed' for a in lot['commitments'] if a['food_bank_id']==bank_id]
            fits=None
            if request:
                probe={"produce_id":"apples","usable_until":request['expires_at']}
                candidate={**request,"chosen_food_bank_ids":[bank_id]}
                fits=bool(self.engine.eligible(candidate,bank,probe,dt(self.engine.now)))
            banks.append({"food_bank_id":bank_id,"name":self.engine.names[bank_id],"area":bank['area'],"pickup_windows":bank['pickup_windows'],"fits_your_pickup_times":fits,"committed_now":committed})
        return 200,{"food_banks":banks}

    def op_choose_food_banks(self, call):
        code,body=call.params['request_code'],call.body
        self.records.get('request',code)
        ids=body['food_bank_ids'] if 'food_bank_ids' in body else body['chosen_food_bank_ids']
        if not isinstance(ids,list) or len(ids)!=len(set(ids)) or any(bank_id not in self.engine.banks for bank_id in ids):
            raise ValueError("choose known, distinct food banks")
        with self.records.transaction():
            request=self.records.get('request',code)
            request['chosen_food_bank_ids']=ids
            self.records.put('request',code,request)
        return 200,{"request_code":code,"chosen_food_bank_ids":ids,"status":"saved","message":SAVED_MESSAGE.get(request.get('language'),SAVED_MESSAGE['en'])}

    def op_get_request(self, call):
        code=call.params['request_code']
        request=self.records.get('request',code)
        # The page's language when it sends one, else the language the household chose.
        language=desk.Language(call.query.get('language') or request['language']).value
        pickups=[{k:v for k,v in pickup.items() if k!='request_code'} | {"items":[{**item,"name":self.item_name(item["produce_id"],language)} for item in pickup["items"]],"wording":self.wording(pickup,request,language)} for pickup in self.records.all('pickup') if pickup['request_code']==code and pickup['status']=='committed']
        return 200,{field:request[field] for field in ('request_code','household_size','fair_share_lb','received_this_week_lb','chosen_food_bank_ids','expires_at')} | {"pickups":pickups,"market_match_tip":None}

    def op_release_pickup(self, call):
        return 200,self.release(call.params['pickup_id'],call.body['request_code'])

    def op_confirm_pickup(self, call):
        body=call.body
        owner=body['food_bank_id']
        self.authorize(owner,call.token)
        with self.records.transaction():
            # Read the pickups and the household's balance inside the transaction that updates them,
            # so two staff confirming at once never count one pickup twice.
            request=self.records.get('request',body['request_code'])
            pending=[pickup for pickup in self.records.all('pickup') if pickup['request_code']==body['request_code'] and pickup['food_bank_id']==owner and pickup['status']=='committed']
            if not pending:
                raise Conflict("no open pickup at this food bank")
            if any(not (dt(pickup['window']['start'])<=dt(self.engine.now)<dt(pickup['window']['end'])) for pickup in pending):
                raise Conflict("pickup is outside its confirmed window")
            for pickup in pending:
                pickup['status']='collected'
                self.records.put('pickup',pickup['pickup_id'],pickup)
                self.records.event(pickup['lot_id'],self.engine.now,'pickup_confirmation',{"pickup_id":pickup['pickup_id'],"pounds":pickup['pounds']})
            collected=sum(pickup['pounds'] for pickup in pending)
            request['received_this_week_lb']+=collected
            self.records.put('request',request['request_code'],request)
        return 200,{"pickup_id":pending[0]['pickup_id'],"request_code":request['request_code'],"food_bank_id":owner,"status":"collected","collected_lb":collected,"received_this_week_lb":request['received_this_week_lb'],"fair_share_lb":request['fair_share_lb'],"confirmed_at":self.engine.now,"items":[item for pickup in pending for item in pickup['items']]}

    def op_voice_intake(self, call):
        body=call.body
        if self.extractor is None:
            return 503,{"error":{"code":"voice_unavailable","message":"Use the text form; voice extraction is not configured"}}
        if not self.voice_allowed():
            return 503,{"error":{"code":"rate_limited","message":"Too many voice calls right now; try again shortly or use the text form"}}
        from harvestnet_agents.llm_negotiators import SpendingCapReached
        transcript=desk.Transcript.from_dict(body.get('transcript',body))
        try:
            draft=desk.intake_transcript(transcript,self.extractor)
        except SpendingCapReached:
            return 503,{"error":{"code":"spending_cap_reached","message":"Voice extraction has reached its spending cap; use the text form"}}
        except desk.ExtractionError:
            return 503,{"error":{"code":"voice_unavailable","message":"Voice extraction failed; use the text form"}}
        return 200,{"call_id":body.get('call_id'),**self.preview(draft),"next":"consent" if draft.is_complete else "ask_missing_questions"}

    # Donors

    def op_list_produce_profiles(self, call):
        calc=self.engine.calc
        profiles=list(calc.profiles.profiles.values())
        return 200,{"profile_set_version":calc.profiles.version,"profiles":[{"produce_id":profile.id,"name":profile.name,"units":list(profile.units),"needs_fridge":profile.needs_fridge,"needs_cold":profile.needs_cold} for profile in profiles],"units_needing_pack_weight":{profile.id:[unit for unit,weight in profile.units.items() if weight is None] for profile in profiles}}

    def op_create_surplus_offer(self, call):
        body,calc=call.body,self.engine.calc
        owner=body['donor_id']
        self.authorize(owner,call.token)
        if owner not in self.engine.donors:
            raise ValueError("unknown donor")
        offer=copy.deepcopy(body)
        offer['lot_id']='lot-'+secrets.token_hex(8)
        offer['reported_at']=self.engine.now
        if dt(offer['deadline'])<=dt(self.engine.now):
            raise ValueError("deadline already passed")
        if not isinstance(offer['items'],list) or not offer['items'] or not all(isinstance(item,dict) for item in offer['items']):
            raise ValueError("an offer needs a list of items")
        basis={}
        for item in offer['items']:
            if item.get('produce_id') not in calc.profiles:
                raise ValueError(f"unknown produce_id {item.get('produce_id')!r}; GET /produce-profiles lists them")
            if item['condition_grade'] not in ('good','use_soon','not_for_people'):
                raise ValueError("condition_grade must be good, use_soon or not_for_people")
            item['usable_until'],basis[item['produce_id']]=self.usable_life(item,owner)
        offer['usable_until_basis']=basis
        if 'drop_off' in body:
            # This offer's drop-off only; the donor's recorded drop-off stays as it is.
            offer['drop_off']=self.drop_off(body['drop_off'])
        draft=self.engine.create_offer(offer)
        negotiate_pending(self.engine,offer['lot_id'])
        return 201,{"lot_id":offer['lot_id'],"version":1,"status":"offered","items":[{"produce_id":item['produce_id'],"name":calc.profiles.get(item['produce_id']).name,"pounds":item['pounds'],"usable_until":item['usable_until'],"usable_until_basis":basis[item['produce_id']]} for item in draft['items']],"needs_human":[item['produce_id'] for item in draft['items'] if item.get('condition_doubt')],"message":"Nothing is promised until every named organization approves."}

    def op_get_lot(self, call):
        lot_id=call.params['lot_id']
        lot=self.records.get('lot',lot_id)
        draft=lot['draft']
        return 200,{"lot_id":lot_id,"donor_id":draft['donor_id'],"status":lot['status'],"current_version":draft['version'],"deadline":draft['deadline'],"items":[self.lot_item(lot,item) for item in draft['items']],"draft":draft,"approvals":list(lot['approvals'].values()),"awaiting_approval_from":[org for org in named(draft) if lot['approvals'].get(org,{}).get('decision')!='approve'],"disagreement":self.disagreement_view(lot)}

    def op_list_lot_versions(self, call):
        lot_id=call.params['lot_id']
        lot=self.records.get('lot',lot_id)
        return 200,{"lot_id":lot_id,"versions":[{"version":version['version'],"proposer_id":version['proposer_id'],"move":"counter" if version['version']>1 else "offer","reason":version['reason'],"change":next((event['data']['amendment'] for event in self.records.events(lot_id) if event['kind']=='amendment' and event['data']['draft']['version']==version['version']),None)} for version in lot['versions']],"current_version":lot['draft']['version']}

    def op_submit_counter(self, call):
        lot_id,body=call.params['lot_id'],call.body
        self.records.get('lot',lot_id)
        self.authorize(body['organization_id'],call.token)
        from harvestnet_agents.negotiation import amendment_from_dict,parse_draft
        with self.records.transaction():
            # The version check and the queued counter share one transaction.
            lot=self.records.get('lot',lot_id)
            draft=lot['draft']
            if body['version']!=draft['version'] or lot['status']=='committed':
                raise Conflict("stale or committed version")
            parse_draft(draft).amend(amendment_from_dict(body['amendment']),proposer_id=body['organization_id'],reason=body['reason'])
            move={"organization_id":body['organization_id'],"version":body['version'],"action":"counter","amendment":body['amendment'],"reason":body['reason']}
            self.records.put('queued_move',lot_id+':'+body['organization_id'],{"lot_id":lot_id,**move})
        negotiate_pending(self.engine,lot_id)
        return 202,{"lot_id":lot_id,"status":"queued_for_turn","based_on_version":draft['version'],"move":move,"message":"Counter queued for your organization's next turn."}

    # Proposed (#1 pending): a condition check, and a food bank's holding and changed version after a disruption.

    def op_record_condition_check(self, call):
        lot_id,body=call.params['lot_id'],call.body
        self.records.get('lot',lot_id)
        self.authorize(body['organization_id'],call.token)
        updated=self.engine.protocol.condition_check(lot_id,body['version'],body['organization_id'],body['produce_id'],body['condition_grade'],body['usable_until'],body['reason'],self.engine.now)
        negotiate_pending(self.engine,lot_id)
        return 200,{'lot_id':lot_id,'version':updated['version'],'status':'condition_recorded','committed':False}

    def op_get_holding(self, call):
        lot_id=call.params['lot_id']
        self.records.get('lot',lot_id)
        self.authorize(call.query.get('food_bank_id'),call.token)
        return 200,changes.holding(self.engine,lot_id,call.query['food_bank_id'])

    def op_propose_change(self, call):
        lot_id,body=call.params['lot_id'],call.body
        self.records.get('lot',lot_id)
        owner=(body.get('terms') or {}).get('proposer_id')
        self.authorize(owner,call.token)
        return 201,changes.propose(self.engine,lot_id,body,owner)

    # Approvals

    def op_list_approvals(self, call):
        owner=call.query.get('organization_id')
        self.authorize(owner,call.token)
        approvals=[]
        for lot in self.records.all('lot'):
            draft=lot['draft']
            if self.awaiting_decision(lot,owner):
                approvals.append({"lot_id":draft['lot_id'],"version":draft['version'],"terms_hash":terms_hash(draft),"requested_at":self.requested_at(lot),"expires_at":draft['deadline'],"why_you":["exact_version_review"],"summary":draft['reason'],"terms":draft,"status":"awaiting_decision"})
        approvals+=changes.pending_approvals(self.records,owner)
        return 200,{"organization_id":owner,"approvals":approvals}

    def op_record_approval(self, call):
        body=call.body
        owner=body.get('organization_id')
        self.authorize_decision(owner,call.token,body)
        receipt={field:body[field] for field in ('lot_id','version','organization_id','terms_hash','decision')}
        if body.get('receipt_id'): receipt['receipt_id']=body['receipt_id']
        if changes.find(self.records,receipt['lot_id'],receipt['version']):
            # A changed version of a committed plan takes its own fresh approvals.
            result=changes.approve(self.engine,receipt,owner)
            return 200,{**receipt,"receipt_id":body.get('receipt_id'),"status":"approval_recorded","change_status":result['status'],"committed":result['committed'],"approved_by":result['approved_by'],"awaiting_approval_from":result['waiting_for']}
        # A committed change supersedes the version it changed. The lot's own draft stays at
        # that earlier version, so a decision on it would otherwise still be accepted.
        if type(receipt['version']) is int:
            newer=[change['version'] for change in changes.changes_for(self.records,receipt['lot_id']) if change['status']=='committed' and change['version']>receipt['version']]
            if newer:
                raise Conflict(f"version {receipt['version']} was superseded by committed version {max(newer)}; decide on the current version")
        result=self.engine.protocol.approve(receipt,owner,self.engine.now,self.engine.validate)
        self.engine.distribute(body['lot_id'])
        reason=result.get('returned_to_negotiation')
        if reason and self.records.get('lot',body['lot_id'])['status']=='negotiating':
            # A decline or an expired hold: the owners' next turns run (design section 8).
            negotiate_pending(self.engine,body['lot_id'])
        return 200,{**receipt,"receipt_id":body.get('receipt_id'),"status":"returned_to_negotiation" if reason else "approval_recorded","committed":result['committed'],"approved_by":result['approved_by'],"awaiting_approval_from":result['waiting_for'],**({"returned_to_negotiation":reason} if reason else {})}

    # Food banks

    def op_update_food_bank_status(self, call):
        bank_id,body=call.params['food_bank_id'],call.body
        self.authorize(bank_id,call.token)
        from harvestnet_agents.negotiation import parse_facts
        with self.records.transaction():
            # Read the status inside the transaction that bumps its version: no lost update.
            bank=self.records.get('bank',bank_id)
            updated={**bank,**{field:body[field] for field in ('storage','pickup_windows','truck','cooler') if field in body}}
            parse_facts('food_bank',{"food_bank_id":bank_id,"name":self.engine.names[bank_id],"demand":self.engine.demand(bank_id),**updated})
            for slot in updated['storage']: number(slot['cold_free_lb']); number(slot['dry_free_lb'])
            updated['status_version']=bank.get('status_version',0)+1
            self.records.put('bank',bank_id,updated)
        return 200,{"food_bank_id":bank_id,"status_version":updated['status_version'],"updated_at":self.engine.now,"message":"Your organization's facts are updated."}

    def op_get_food_bank_dashboard(self, call):
        bank_id,calc=call.params['food_bank_id'],self.engine.calc
        self.authorize(bank_id,call.token)
        bank=self.records.get('bank',bank_id)
        incoming=[]
        arrivals=[]
        disagreements=[]
        for lot in self.records.all('lot'):
            draft=lot['draft']
            allocations=[a for a in draft['allocations'] if a['food_bank_id']==bank_id]
            if lot['status']=='preserved_disagreement' and any(a['food_bank_id']==bank_id for version in lot['versions'] for a in version['allocations']):
                # Involved if it was ever on the table, even when the last plan left this food bank out.
                view=self.disagreement_view(lot)
                disagreements.append({"lot_id":draft['lot_id'],"reason":view['reason'],"options":view['options'],"reasons":view['reasons']})
            if not allocations: continue
            transport=next((t for t in draft['transports'] if t['food_bank_id']==bank_id),None)
            suggests,why=self.suggestion(lot,bank_id)
            incoming.append({"lot_id":draft['lot_id'],"version":draft['version'],"donor_id":draft['donor_id'],"donor_name":self.engine.names[draft['donor_id']],"for_us":[{"produce_id":a['produce_id'],"name":calc.profiles.get(a['produce_id']).name,"pounds":a['pounds']} for a in allocations],"transport":transport,"agent_suggests":suggests,"agent_reason":why,"needs_your_approval":self.awaiting_decision(lot,bank_id)})
            if transport: arrivals.append({"lot_id":draft['lot_id'],"version":draft['version'],"arrives_at":transport['arrives_at'],"items":allocations,"status":lot['status']})
            if lot.get('stop_reason') and lot['status']!='preserved_disagreement': disagreements.append({"lot_id":draft['lot_id'],"reason":lot['stop_reason']})
        return 200,{"food_bank_id":bank_id,"name":self.engine.names[bank_id],"capacity":{field:bank.get(field) for field in ('storage','pickup_windows','truck','cooler')},"incoming_offers":incoming,"fair_share_gap":self.engine.demand(bank_id),"disagreements":disagreements,"expected_arrivals":arrivals,"disruptions":changes.summaries(self.records,bank_id)}

    # Results

    def op_get_results(self, call):
        try:
            return 200,self.records.get('results',call.query['scenario_id'])
        except NotFound:
            return 404,{"error":{"code":"not_found","message":"No evaluation published for this scenario; run python -m harvestnet_core evaluate"}}
