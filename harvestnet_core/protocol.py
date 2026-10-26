"""Owner-authenticated holds and exact-version human approvals.

Scheduling and recording are shared. Decisions remain with each organization.
"""
import copy
from datetime import datetime
import math
from harvestnet_agents.terms import terms_hash


class Conflict(ValueError):
    pass


def dt(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return result


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("a finite nonnegative number is required")
    return float(value)


def named(draft):
    return sorted({draft["donor_id"]} | {a["food_bank_id"] for a in draft["allocations"] if a["pounds"] > 0})


class Protocol:
    def __init__(self, records):
        self.records = records

    def create(self, draft, now, extra=None):
        from harvestnet_agents.negotiation import parse_draft
        if type(draft['version']) is not int or draft['version']<1:
            raise ValueError('positive integer version required')
        parse_draft(draft)
        for item in draft["items"]:
            number(item["pounds"])
        with self.records.transaction():
            try:
                self.records.get("lot", draft["lot_id"])
            except KeyError:
                pass
            else:
                raise Conflict("lot already exists")
            # ``extra`` holds offer facts outside the shared draft, such as this offer's drop-off.
            self.records.put("lot", draft["lot_id"], {**copy.deepcopy(extra or {}), "draft": draft, "versions": [copy.deepcopy(draft)], "status": "negotiating", "approvals": {}, "holds": {}, "commitments": []})
            self.records.event(draft["lot_id"], now, "draft", draft)

    def amend(self, lot_id, version, organization_id, amendment, reason, now):
        from harvestnet_agents.negotiation import parse_draft, amendment_from_dict
        if 'pounds' in amendment:
            number(amendment['pounds'])
        with self.records.transaction():
            lot = self.records.get("lot", lot_id)
            draft = lot["draft"]
            if organization_id not in draft.get('names',{}):
                raise ValueError('unknown proposing organization')
            if draft["version"] != version or lot["status"] == "committed":
                raise Conflict("stale or committed version")
            if not reason.strip():
                raise ValueError("a reason is required")
            # The typed amendment validates conservation and legal transport values.
            updated = parse_draft(draft).amend(amendment_from_dict(amendment), proposer_id=organization_id, reason=reason)
            from dataclasses import asdict
            from .engine import jsonable
            draft = jsonable(updated)
            # Enum subclasses serialize as strings.
            lot.update(draft=draft, approvals={}, holds={},status='negotiating')
            lot.pop('stop_reason',None)
            lot["versions"].append(copy.deepcopy(draft))
            self.records.put("lot", lot_id, lot)
            self.records.event(lot_id, now, "amendment", {"organization_id": organization_id, "amendment": amendment, "draft": draft})
            return draft

    def hold(self, lot_id, version, owner, holds, now, capacities):
        with self.records.transaction():
            lot = self.records.get("lot", lot_id)
            if lot["draft"]["version"] != version or owner not in named(lot["draft"]):
                raise Conflict("stale version or unnamed owner")
            if not holds:
                raise ValueError("owner must reserve resources")
            for h in holds:
                amount = number(h.get("pounds") or 0)
                start, end = dt(h["start"]), dt(h["end"])
                if start >= end or end <= dt(now):
                    raise Conflict("hold is expired or has an empty interval")
                if h["resource"] not in capacities:
                    raise ValueError("resource does not belong to this owner")
                existing = []
                for other in self.records.all("lot"):
                    if other["draft"]["lot_id"] == lot_id:
                        continue
                    if h['resource']=='lot':
                        # Each lot is distinct inventory, not another claim on this lot.
                        continue
                    existing.extend(other.get("holds", {}).get(owner, []))
                overlapping = [x for x in existing + holds if x["resource"] == h["resource"] and dt(x["start"]) < end and start < dt(x["end"])]
                # Sweep each boundary; pairwise sums wrongly reject nonconcurrent holds.
                for at in {start} | {dt(x["start"]) for x in overlapping if start <= dt(x["start"]) < end}:
                    total = sum(number(x.get("pounds") or 0) for x in overlapping if dt(x["start"]) <= at < dt(x["end"]))
                    if total > number(capacities[h["resource"]]) + 1e-8:
                        raise Conflict("resource would be double booked")
            lot["holds"][owner] = copy.deepcopy(holds)
            self.records.put("lot", lot_id, lot)
            self.records.event(lot_id, now, "owner_hold", {"organization_id": owner, "version": version, "holds": holds})

    def condition_check(self, lot_id, version, owner, produce_id, grade, usable_until, reason, now):
        if grade not in ('good','use_soon','not_for_people') or not reason.strip():
            raise ValueError('condition grade and a reason are required')
        if dt(usable_until)<=dt(now):
            raise ValueError('condition check must state a future usable time')
        with self.records.transaction():
            lot=self.records.get('lot',lot_id)
            old=lot['draft']
            if old['version']!=version or lot['status']=='committed':
                raise Conflict('stale or committed version')
            if owner!=old['donor_id'] and not any(a['food_bank_id']==owner and a['produce_id']==produce_id for a in old['allocations']):
                raise ValueError('condition check belongs to the donor or receiving food bank')
            draft=copy.deepcopy(old)
            item=next((i for i in draft['items'] if i['produce_id']==produce_id),None)
            if item is None:
                raise ValueError(f'produce {produce_id!r} is not in lot {lot_id!r}')
            item.update(condition_grade=grade,usable_until=usable_until,condition_doubt=None)
            draft.update(version=version+1,based_on_version=version,proposer_id=owner,reason=reason)
            lot.update(draft=draft,approvals={},holds={},status='negotiating')
            lot.setdefault('usable_until_basis',{})[produce_id]={'kind':'condition_check','organization_id':owner}
            lot['versions'].append(copy.deepcopy(draft))
            self.records.put('lot',lot_id,lot)
            self.records.event(lot_id,now,'human_condition_check',{'organization_id':owner,'produce_id':produce_id,'version':draft['version'],'grade':grade,'reason':reason})
            return draft

    def _expire_holds(self, lot, now):
        """Design section 8, Held to Negotiating: a hold ran out before every approval was in.

        The stale holds go, the exact terms need fresh holds and fresh approvals, and the owners'
        next turns run. Nothing commits (ADR 0004). Returns whether the lot went back."""
        draft = lot["draft"]
        expired = sorted(o for o in named(draft) if any(dt(now) >= dt(h["end"]) for h in lot["holds"].get(o, [])))
        if not expired or lot["status"] == "committed":
            return False
        for o in expired:
            lot["holds"].pop(o, None)
        lot.update(approvals={}, status="negotiating")
        self.records.event(draft["lot_id"], now, "hold_expired", {"version": draft["version"], "organizations": expired})
        return True

    def expire_holds(self, lot_id, now):
        """Send a lot whose holds ran out back to negotiation. Returns whether it went back."""
        with self.records.transaction():
            lot = self.records.get("lot", lot_id)
            if not self._expire_holds(lot, now):
                return False
            self.records.put("lot", lot_id, lot)
            return True

    def approve(self, receipt, owner, now, validate):
        lot_id = receipt["lot_id"]
        if type(receipt['version']) is not int or receipt['version']<1:
            raise ValueError('positive integer version required')
        if owner != receipt["organization_id"]:
            raise ValueError("an organization cannot approve for another")
        if receipt["decision"] not in ("approve", "decline"):
            raise ValueError("explicit human decision required")
        with self.records.transaction():
            rid = receipt.get("receipt_id")
            if rid:
                try:
                    previous = self.records.get("receipt", rid)
                except KeyError:
                    pass
                else:
                    if previous["receipt"] != receipt:
                        raise Conflict("receipt ID reused with different terms")
                    return previous["result"]
            lot = self.records.get("lot", lot_id)
            draft = lot["draft"]
            if any(m['lot_id']==lot_id for m in self.records.all('queued_move')):
                raise Conflict('an owner counter is awaiting its published turn')
            if receipt["version"] != draft["version"] or receipt["terms_hash"] != terms_hash(draft):
                raise Conflict("stale version or changed terms")
            if owner not in named(draft) or dt(now) >= dt(draft["deadline"]):
                raise Conflict("unnamed organization or deadline passed")
            if receipt["decision"] == "approve" and self._expire_holds(lot, now):
                self.records.put("lot", lot_id, lot)
                result = {"lot_id": lot_id, "version": draft["version"], "decision_recorded": False, "returned_to_negotiation": "hold_expired",
                          "approved_by": [], "waiting_for": named(draft), "committed": False}
                if rid:
                    self.records.put("receipt", rid, {"receipt": receipt, "result": result})
                return result
            lot["approvals"][owner] = copy.deepcopy(receipt)
            self.records.event(lot_id, now, "human_decision", receipt)
            waiting = [o for o in named(draft) if lot["approvals"].get(o, {}).get("decision") != "approve"]
            returned = None
            if receipt["decision"] == "decline" and lot["status"] != "committed":
                # A human's decline ends this version's chance to commit. The lot goes back to
                # negotiation: the holds are released and the owners' next turns run. The decline
                # stays on the version, so these exact terms are never sent for approval again.
                lot.update(holds={}, status="negotiating")
                self.records.event(lot_id, now, "returned_to_negotiation", {"version": draft["version"], "reason": "human_declined", "organization_id": owner})
                returned = "human_declined"
            holds_valid = all(lot["holds"].get(o) and all(dt(now) < dt(h["end"]) for h in lot["holds"][o]) for o in named(draft))
            if not waiting and holds_valid and lot["status"] != "committed":
                validate(draft, lot["holds"])
                lot["status"] = "committed"
                lot["commitments"] = copy.deepcopy(draft["allocations"])
                self.records.event(lot_id, now, "commitment", {"version": draft["version"], "terms_hash": terms_hash(draft), "allocations": lot["commitments"], "approvals": lot["approvals"], "holds": lot["holds"]})
            self.records.put("lot", lot_id, lot)
            result = {"lot_id": lot_id, "version": draft["version"], "decision_recorded": True, "approved_by": sorted(o for o, r in lot["approvals"].items() if r["decision"] == "approve"), "waiting_for": waiting, "committed": lot["status"] == "committed"}
            if returned:
                result["returned_to_negotiation"] = returned
            if rid:
                self.records.put("receipt", rid, {"receipt": receipt, "result": result})
            return result
