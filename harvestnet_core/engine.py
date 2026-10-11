"""A scripted clock and owner-by-owner moves; never a supervisor policy."""
import copy
from dataclasses import asdict, is_dataclass
from datetime import timedelta, time
import re
import uuid
from harvestnet_agents.negotiation import parse_agent_input, parse_draft, parse_facts, Role
from harvestnet_agents.rules_negotiators import rules_negotiator
from harvestnet_agents.calculators import HouseholdBalance
from .calculators import Calculators
from .protocol import Protocol, Conflict, dt, number, named, terms_hash
from .records import Records
from .checks import rule_checks


def jsonable(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class Engine:
    def __init__(self, fixture, records=None, calculators=None):
        self.fixture = copy.deepcopy(fixture)
        self.records = records or Records()
        self.protocol = Protocol(self.records)
        # The real calculators by default. The join (#20) passes them wrapped so every call
        # is logged and compared with the stand-ins; the answers are still the real ones.
        self.calc = calculators if calculators is not None else Calculators()
        self.policy_session=uuid.uuid4().hex
        self.negotiators={}
        self.now = fixture["clock"]["start"]
        self.names = {o["organization_id"]: o["name"] for o in fixture["organizations"]}
        self.roles = {o["organization_id"]: o["role"] for o in fixture["organizations"]}
        self.banks = {b["organization_id"]: b for b in self.fixture["food_banks"]}
        self.donors = {d["organization_id"]: d for d in self.fixture["donors"]}
        with self.records.transaction():
            for b in self.banks.values():
                try:
                    self.records.get("bank", b["organization_id"])
                except KeyError:
                    self.records.put("bank", b["organization_id"], b)
            for r in fixture["requests"]:
                share = self.calc.fair_share(r["household_size"])
                record = {**r, "fair_share_lb": share.pounds, "table_version": share.table_version, "expires_at": (dt(r["submitted_at"])+timedelta(days=7)).isoformat(), "initial_received_lb": r.get("received_this_week_lb",0)}
                try:
                    self.records.get("request", r["request_code"])
                except KeyError:
                    self.records.put("request", r["request_code"], record)
        # Scripted faults are public fixture facts for every comparison method.
        # Reserve conservatively when a known cold-space loss precedes collection.
        # This is a fixture forecast, not a claim of live Directory rediscovery.
        for fault in fixture.get("faults", []):
            if fault["kind"] != "cooler_failure":
                raise ValueError("unsupported fixture fault")
            bid = fault["food_bank_id"]
            bank = self.records.get("bank", bid)
            if any(dt(w["end"]) > dt(fault["at"]) for w in bank["pickup_windows"]):
                for s in bank["storage"]:
                    s["cold_free_lb"] = 0
                with self.records.transaction():
                    self.records.put("bank", bid, bank)

    def rules_for(self, role, organization):
        key=(role,organization)
        if key not in self.negotiators:
            self.negotiators[key]=rules_negotiator(role,organization,self.calc)
        return self.negotiators[key]

    def reserved(self, code):
        return sum(p["pounds"] for p in self.records.all("pickup") if p["request_code"] == code and p["status"] == "committed")

    def eligible(self, request, bank, item, arrival):
        exclusions={str(x).strip().casefold() for x in request['cant_eat']}
        profile=self.calc.profiles.get(item['produce_id'])
        if bank["organization_id"] not in request.get("chosen_food_bank_ids", []) or item["produce_id"].casefold() in exclusions or profile.name.casefold() in exclusions or dt(request["expires_at"]) <= dt(self.now):
            return None
        needs_cold = self.calc.profiles.get(item["produce_id"]).needs_cold
        for window in bank["pickup_windows"]:
            start, end = max(dt(window["start"]), arrival), min(dt(window["end"]), dt(item["usable_until"]))
            if request["limited_fridge"] and needs_cold and start.date() != arrival.date():
                continue
            for hw in request["pickup_windows"]:
                day = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[start.weekday()]
                if day not in hw["days"]:
                    continue
                hs = start.replace(hour=int((hw.get("start") or "00:00").split(":")[0]), minute=int((hw.get("start") or "00:00").split(":")[1]), second=0)
                he = start.replace(hour=int((hw.get("end") or "23:59").split(":")[0]), minute=int((hw.get("end") or "23:59").split(":")[1]), second=0)
                lo, hi = max(start, hs), min(end, he)
                if lo < hi:
                    return {"start": lo.isoformat(), "end": hi.isoformat()}
        return None

    def demand(self, bank_id):
        rs = [r for r in self.records.all("request") if bank_id in r.get("chosen_food_bank_ids", []) and dt(r["expires_at"]) > dt(self.now)]
        gap = self.calc.fair_share_gap([HouseholdBalance(r["household_size"], r.get("received_this_week_lb",0)+self.reserved(r["request_code"])) for r in rs])
        return {"households":len(rs), "people":sum(r["household_size"] for r in rs), "below_fair_share_lb":gap.gap_lb, "limited_fridge":sum(r["limited_fridge"] for r in rs), "evening_only":sum(all((w.get("start") or "00:00") >= "18:00" for w in r["pickup_windows"]) for r in rs), "table_version":gap.table_version}

    def facts(self, org, draft, declined=()):
        role = self.roles[org]
        donor = self.donors[draft["donor_id"]]
        if role == "donor":
            return {"donor_id":org, "travel_minutes":donor["travel_minutes"], "drop_off":donor.get("drop_off")}
        if role == "food_bank":
            bank = self.records.get("bank", org)
            return {"food_bank_id":org, "name":self.names[org], "storage":bank["storage"], "pickup_windows":bank["pickup_windows"], "truck":bank.get("truck"), "travel_minutes_from_donor":donor["travel_minutes"].get(org), "demand":self.demand(org)}
        return {"gaps":[{"food_bank_id":bid,"name":self.names[bid],"households":self.demand(bid)["households"],"below_fair_share_lb":self.demand(bid)["below_fair_share_lb"],"low_access":b["low_access"]} for bid,b in self.banks.items()], "declined":list(declined)}

    def create_offer(self, offer):
        if offer.get("recall_notice"):
            raise ValueError("recalled lots are never offered")
        items = [{"produce_id":i["produce_id"], "pounds":self.calc.to_pounds(i["produce_id"],i["quantity"],i["unit"],i.get("lb_per_unit")), "condition_grade":i["condition_grade"], "usable_until":i["usable_until"], "condition_doubt":i.get("condition_doubt")} for i in offer["items"]]
        if len({i["produce_id"] for i in items}) != len(items):
            raise ValueError("combine duplicate produce lines before reporting")
        drop = self.donors[offer["donor_id"]].get("drop_off")
        # Version 1 publishes where the donor offered to drop off (agent-moves.md: drop_off_to),
        # from the donor's own recorded route, so food banks without a truck can bid (#20).
        draft = {"lot_id":offer["lot_id"], "version":1,"donor_id":offer["donor_id"], "deadline":offer["deadline"], "items":items,"allocations":[],"transports":[],"drop_off_to":list(drop["food_bank_ids"]) if drop else [],"drop_off_refrigerated":bool(drop.get("refrigerated",False)) if drop else False,"proposer_id":offer["donor_id"],"reason":"Owner reported surplus; nothing committed", "based_on_version":None,"names":self.names}
        self.protocol.create(draft, self.now)
        return draft

    def capacities(self, owner, draft):
        if owner == draft["donor_id"]:
            drop = self.donors[owner].get("drop_off")
            return {"lot":sum(i["pounds"] for i in draft["items"]), "drop_off": drop["capacity_lb"] if drop else 0}
        bank = self.records.get("bank", owner)
        return {"storage_cold": min((s["cold_free_lb"] for s in bank["storage"]),default=0), "storage_dry":min((s["dry_free_lb"] for s in bank["storage"]),default=0), "truck":bank["truck"]["capacity_lb"] if bank.get("truck") else 0}

    def validate(self, draft, holds):
        parse_draft(draft)
        transports = {t["food_bank_id"]:t for t in draft["transports"]}
        for org in named(draft):
            expected = "lot" if org == draft["donor_id"] else None
            if expected and sum(h.get("pounds") or 0 for h in holds.get(org,[]) if h["resource"]==expected) + 1e-8 < sum(a["pounds"] for a in draft["allocations"]):
                raise Conflict("lot hold does not cover allocation")
        drop_total = sum(a["pounds"] for a in draft["allocations"] if transports.get(a["food_bank_id"],{}).get("mover")=="donor")
        drop = self.donors[draft["donor_id"]].get("drop_off")
        if drop_total and (not drop or drop_total > drop["capacity_lb"] + 1e-8):
            raise Conflict("donor drop-off capacity exceeded")
        if drop_total and sum(h.get('pounds') or 0 for h in holds.get(draft['donor_id'],[]) if h['resource']=='drop_off')+1e-8 < drop_total:
            raise Conflict('drop-off hold does not cover donor route')
        for bid in {a["food_bank_id"] for a in draft["allocations"] if a["pounds"]>0}:
            if bid not in transports:
                raise Conflict("missing transport")
            t = transports[bid]
            bank = self.records.get("bank", bid)
            arrival, depart = dt(t["arrives_at"]), dt(t["departs_at"])
            if depart > dt(draft["deadline"]) or arrival < depart:
                raise Conflict("transport misses donor deadline")
            minimum = self.calc.arrival_time(depart, self.donors[draft["donor_id"]]["travel_minutes"][bid])
            if arrival < minimum:
                raise Conflict("transport is faster than recorded travel")
            facts = parse_facts("food_bank", self.facts(bid,draft))
            capacity = self.calc.storage_at(facts.storage,arrival)
            cold = dry = total = 0
            for a in [a for a in draft["allocations"] if a["food_bank_id"]==bid and a["pounds"]>0]:
                item = next(i for i in draft["items"] if i["produce_id"]==a["produce_id"])
                if item["condition_grade"]=="not_for_people" or item.get("condition_doubt"):
                    raise Conflict("condition needs an explicit cleared check")
                profile = self.calc.profiles.get(item["produce_id"])
                cold += a["pounds"] if profile.needs_cold else 0
                dry += a["pounds"] if not profile.needs_cold else 0
                total += a["pounds"]
                resource='storage_cold' if profile.needs_cold else 'storage_dry'
                held=[h for h in holds.get(bid,[]) if h['resource']==resource and dt(h['start'])<=arrival<dt(h['end'])]
                if not held:
                    raise Conflict('missing storage reservation through collection')
                last=min(dt(h['end']) for h in held)
                pickup_bank={**bank,'pickup_windows':[{'start':w['start'],'end':min(dt(w['end']),last).isoformat()} for w in bank['pickup_windows'] if dt(w['start'])<last]}
                if not any(self.eligible(r,pickup_bank,item,arrival) for r in self.records.all("request")):
                    raise Conflict("no eligible household pickup before spoilage")
            if cold > capacity.cold_free_lb+1e-8 or dry > capacity.dry_free_lb+1e-8:
                raise Conflict("storage capacity exceeded")
            for resource, needed in (("storage_cold",cold),("storage_dry",dry)):
                if needed and sum(h.get("pounds") or 0 for h in holds.get(bid,[]) if h["resource"]==resource and dt(h["start"]) <= arrival < dt(h["end"]))+1e-8 < needed:
                    raise Conflict("storage hold does not cover allocation at arrival")
            mover = bank.get("truck") if t["mover"]=="food_bank" else drop
            if not mover or total > mover["capacity_lb"]+1e-8 or not (dt(mover["window"]["start"]) <= depart < arrival <= dt(mover["window"]["end"])) or (cold and not mover["refrigerated"]):
                raise Conflict("transport exceeds owner's capability")
            if t["mover"]=="donor" and bid not in drop["food_bank_ids"]:
                raise Conflict("destination is not on donor's route")
            if t['mover']=='food_bank' and sum(h.get('pounds') or 0 for h in holds.get(bid,[]) if h['resource']=='truck' and dt(h['start'])<=depart and dt(h['end'])>=arrival)+1e-8 < total:
                raise Conflict('truck hold does not cover transport')

    def distribute(self, lot_id):
        lot = self.records.get("lot",lot_id)
        if lot["status"] != "committed":
            return
        if any(p["lot_id"]==lot_id for p in self.records.all("pickup")):
            return
        d=lot["draft"]
        with self.records.transaction():
            for a in d["allocations"]:
                if a["pounds"]<=0:
                    continue
                bank=self.records.get("bank",a["food_bank_id"])
                item=next(i for i in d["items"] if i["produce_id"]==a["produce_id"])
                arrival=dt(next(t["arrives_at"] for t in d["transports"] if t["food_bank_id"]==a["food_bank_id"]))
                resource='storage_cold' if self.calc.profiles.get(item['produce_id']).needs_cold else 'storage_dry'
                last=min(dt(h['end']) for h in lot['holds'][a['food_bank_id']] if h['resource']==resource and dt(h['start'])<=arrival<dt(h['end']))
                bank={**bank,'pickup_windows':[{'start':w['start'],'end':min(dt(w['end']),last).isoformat()} for w in bank['pickup_windows'] if dt(w['start'])<last]}
                rs=[r for r in self.records.all("request") if self.eligible(r,bank,item,arrival)]
                portions=self.calc.household_portions(a["pounds"],[{"request_code":r["request_code"],"household_size":r["household_size"],"received_lb":r.get("received_this_week_lb",0)+self.reserved(r["request_code"])} for r in rs])
                for portion in portions["portions"]:
                    if portion["pounds"]<1e-8:
                        continue
                    r=next(r for r in rs if r["request_code"]==portion["request_code"])
                    pid=f"pk-{lot_id}-{len(self.records.all('pickup'))+1}"
                    pickup={"pickup_id":pid,"request_code":r["request_code"],"food_bank_id":a["food_bank_id"],"food_bank_name":self.names[a["food_bank_id"]],"window":self.eligible(r,bank,item,arrival),"items":[{"produce_id":item["produce_id"],"name":self.calc.profiles.get(item["produce_id"]).name,"pounds":portion["pounds"]}],"pounds":portion["pounds"],"lot_id":lot_id,"version":d["version"],"status":"committed"}
                    self.records.put("pickup",pid,pickup)
                    self.records.event(lot_id,self.now,"pickup_notice",pickup)

    def pathways(self, lot_id):
        lot=self.records.get("lot",lot_id)
        result=[]
        for item in lot["draft"]["items"]:
            allocated=0
            for a in lot["commitments"]:
                if a["produce_id"]==item["produce_id"]:
                    allocated+=a["pounds"]
                    result.append({**a,"status":"committed","reason":"Exact-version human approvals and owner resource holds"})
            if item["pounds"]>allocated+1e-8:
                result.append({"produce_id":item["produce_id"],"pounds":item["pounds"]-allocated,"status":"unclaimed","reason":lot.get("stop_reason","No approved feasible pathway")})
        return result


def run_fixture(fixture, move_provider=None, *, records=None, calculators=None, observer=None):
    """Run every lot in a fixture. ``calculators`` defaults to the real ones.

    ``observer`` (the #20 join's ``HarnessLog``) only watches: it is told when a turn
    starts, when the mover's facts are ready, when its move is recorded, and when a lot
    is finished. It never changes a move, a record, or the clock."""
    engine=Engine(fixture,records,calculators)
    if observer: observer.attach(engine)
    result={"commitments":[],"pathways":[],"rule_checks":{},"mode":fixture["mode"],"synthetic":fixture["synthetic"],"scenario_id":fixture["scenario_id"],"calculator_label":engine.calc.label,"policy_label":getattr(move_provider,'label','real rules-based negotiators' if move_provider is None else 'configured policy adapter'),"scripted_humans":True,"events":[]}
    checks=[]
    for offer in fixture["surplus_offers"]:
        engine.now=offer["reported_at"]
        if offer.get("recall_notice"):
            engine.records.event(offer["lot_id"],engine.now,"recall_refused",{"reason":"recall notice"})
            if observer: observer.lot_finished(engine,offer["lot_id"])
            continue
        engine.create_offer(offer)
        lot_id=offer["lot_id"]
        accepts=set()
        unchanged=0
        declined=[]
        rounds=fixture["policies"]["rounds_without_new_terms_before_disagreement"]
        stop_reason=None
        for turn in range(1,201):
            lot=engine.records.get("lot",lot_id)
            draft=lot["draft"]
            org=fixture["turn_order"][(turn-1)%len(fixture["turn_order"])]
            if (turn-1)%len(fixture["turn_order"])==0:
                round_start_version=draft["version"]
            if observer: observer.turn_started(engine,lot_id,org)
            input={"role":engine.roles[org],"draft":draft,"facts":engine.facts(org,draft,declined),"turn":{"organization_id":org,"number":turn,"now":engine.now,"accepted_by":sorted(accepts)}}
            if observer: observer.facts_ready(engine,lot_id,org,input)
            queued_id=lot_id+':'+org
            try:
                queued=engine.records.get('queued_move',queued_id)
            except KeyError:
                queued=None
            from harvestnet_agents.llm_negotiators import NumberPool, precompute, text_number_problems
            call_start=len(engine.calc.calls)
            role, typed=parse_agent_input(input)
            pool=NumberPool()
            pool.add(typed)
            pool.add(precompute(role,typed,engine.calc))
            if move_provider:
                wire={**input,"turn":org,"turn_context":input["turn"],"policy_session":engine.policy_session}
                move=move_provider(org,wire)
            else:
                move=engine.rules_for(role,org).move(typed).to_dict()
            if move_provider and hasattr(move_provider,'pop_metadata'):
                metadata=move_provider.pop_metadata()
                if metadata:
                    engine.records.event(lot_id,engine.now,'policy_provenance',{'organization_id':org,**metadata})
                    count=metadata.get('number_check_failures',0)
                    if count:
                        engine.records.event(lot_id,engine.now,'number_check_failure',{'count':count,'organization_id':org,'problems':['reported by validated LLM policy']})
                        current=engine.records.get('lot',lot_id)
                        current['number_check_failures']=current.get('number_check_failures',0)+count
                        with engine.records.transaction(): engine.records.put('lot',lot_id,current)
            if queued:
                with engine.records.transaction():
                    engine.records.delete('queued_move',queued_id)
                if queued['version']==draft['version']:
                    move={k:v for k,v in queued.items() if k!='lot_id'}
                else:
                    engine.records.event(lot_id,engine.now,'stale_counter_refused',{'organization_id':org,'version':queued['version']})
            for call in engine.calc.calls[call_start:]:
                pool.add(call.result)
            problems=text_number_problems(move.get('reason',''),pool)
            if problems:
                engine.records.event(lot_id,engine.now,'number_check_failure',{'count':1,'organization_id':org,'problems':problems})
                lot=engine.records.get('lot',lot_id)
                lot['number_check_failures']=lot.get('number_check_failures',0)+1
                with engine.records.transaction(): engine.records.put('lot',lot_id,lot)
                # Re-ask the same owner once. Then deterministic validated fallback.
                if move_provider:
                    retry=move_provider(org,wire)
                    if text_number_problems(retry.get('reason',''),pool):
                        engine.records.event(lot_id,engine.now,'number_check_failure',{'count':1,'organization_id':org,'problems':['second failed number check']})
                        lot['number_check_failures']+=1
                        with engine.records.transaction(): engine.records.put('lot',lot_id,lot)
                        move=engine.rules_for(role,org).move(typed).to_dict()
                        move['reason']='Validated deterministic owner fallback; human approval is still required.'
                        engine.records.event(lot_id,engine.now,'template_fallback',{'organization_id':org})
                    else:
                        move=retry
                else:
                    move['reason']='Validated deterministic owner move; human approval is still required.'
            if move.get("organization_id")!=org or move.get("version")!=draft["version"] or not move.get("reason"):
                raise ValueError("move violates published turn/version")
            engine.records.event(lot_id,engine.now,"move",move)
            if observer: observer.move_made(engine,lot_id,org,input,move)
            action=move["action"]
            if org=="advocate" and action not in ("counter","pass"):
                raise ValueError("advocate cannot vote")
            if action=="counter":
                old=copy.deepcopy(draft)
                updated=engine.protocol.amend(lot_id,draft["version"],org,move["amendment"],move["reason"],engine.now)
                if move["amendment"]["kind"]=="set_pounds" and engine.roles[org]=="food_bank":
                    declined.append({"food_bank_id":org,"produce_id":move["amendment"]["produce_id"]})
                accepts.clear()
            elif action=="accept":
                accepts.add(org)
            elif action=="request_hold":
                if move.get("resource_owner")!=org:
                    raise ValueError("resource owner mismatch")
                engine.protocol.hold(lot_id,draft["version"],org,move["holds"],engine.now,engine.capacities(org,draft))
            elif action not in ("reject","pass","ask_human"):
                raise ValueError("unknown move")
            lot=engine.records.get("lot",lot_id)
            d=lot["draft"]
            if d["allocations"] and all(lot["holds"].get(o) for o in named(d)):
                for human in fixture.get("humans",[]):
                    owner=human["organization_id"]
                    if owner not in named(d) or owner in lot["approvals"]:
                        continue
                    at=dt(offer["reported_at"])+timedelta(minutes=human["after_minutes"])
                    engine.now=max(dt(engine.now),at).isoformat()
                    receipt={"lot_id":lot_id,"version":d["version"],"organization_id":owner,"terms_hash":terms_hash(d),"decision":human["on_approval_request"],"receipt_id":f"script-{lot_id}-{d['version']}-{owner}"}
                    try:
                        engine.protocol.approve(receipt,owner,engine.now,engine.validate)
                    except Conflict as exc:
                        engine.records.event(lot_id,engine.now,"commitment_refused",{"reason":str(exc)})
                        break
                if engine.records.get("lot",lot_id)["status"]=="committed":
                    break
            if turn%len(fixture["turn_order"])==0:
                # A round counts toward the stop rule only if nobody changed the terms in it.
                unchanged=unchanged+1 if engine.records.get("lot",lot_id)["draft"]["version"]==round_start_version else 0
                if unchanged>=rounds:
                    stop_reason=f"{rounds} rounds without new terms; no automatic commitment"
                    break
        lot=engine.records.get("lot",lot_id)
        if lot["status"]!="committed":
            with engine.records.transaction():
                lot["status"]="preserved_disagreement"
                lot["stop_reason"]=stop_reason or "Turn limit reached without an approved feasible pathway; no automatic commitment"
                engine.records.put("lot",lot_id,lot)
                engine.records.event(lot_id,engine.now,"preserved_disagreement",{"reason":lot["stop_reason"]})
        engine.distribute(lot_id)
        for fault in fixture.get('faults',[]):
            engine.records.event(lot_id,fault['at'],'scripted_cooler_failure',{'food_bank_id':fault['food_bank_id'],'reading':fault['reading'],'synthetic':True,'handling':'Known fixture fault excluded unsafe cold reservations before commitment; live rediscovery belongs to the cooler-failure adapter'})
        from .api import API
        api=API(engine,clock=lambda:engine.now)
        for reply in fixture.get("household_replies",[]):
            for p in engine.records.all("pickup"):
                if p['lot_id']==lot_id and p['request_code']==reply['request_code'] and reply['on_pickup_notice']=='cant_make_it' and p['status']=='committed':
                    engine.now=p['window']['start']
                    api.release(p['pickup_id'],p['request_code'])
                if p["lot_id"]==lot_id and p["request_code"]==reply["request_code"] and reply["on_pickup_notice"]=="collect":
                    with engine.records.transaction():
                        p["status"]="collected"
                        engine.records.put("pickup",p["pickup_id"],p)
                        r=engine.records.get("request",p["request_code"])
                        r["received_this_week_lb"]=r.get("received_this_week_lb",0)+p["pounds"]
                        engine.records.put("request",r["request_code"],r)
                        engine.records.event(lot_id,p["window"]["start"],"pickup_confirmation",{"pickup_id":p["pickup_id"],"pounds":p["pounds"]})
        pathways=engine.pathways(lot_id)
        caps={(o,r):v for o in named(lot["draft"]) for r,v in engine.capacities(o,lot["draft"]).items()}
        checks.append(rule_checks(engine.records,lot_id,pathways,caps))
        if observer: observer.lot_finished(engine,lot_id)
        result["commitments"].extend(engine.records.get("lot",lot_id)["commitments"])
        result["pathways"].extend(pathways)
        result["events"].extend(engine.records.events(lot_id))
    result["rule_checks"]={k:all(c[k] for c in checks) for k in checks[0]} if checks else {"zero_invalid_commitments":False}
    return result
