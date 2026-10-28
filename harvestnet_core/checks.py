"""Recompute audit checks from stored evidence, not a constant success flag."""
from collections import defaultdict
from harvestnet_agents.terms import terms_hash
from .protocol import dt, number, named


def rule_checks(records, lot_id, pathways, capacities):
    capacities=dict(capacities)
    lot = records.get("lot", lot_id)
    events = records.events(lot_id)
    commitments = [e for e in events if e["kind"] == "commitment"]
    versions = {d["version"]: d for d in lot["versions"]}
    approval_ok = True
    holds_ok = True
    for event in commitments:
        data = event["data"]
        draft = versions[data["version"]]
        approvals = data["approvals"]
        approval_ok &= all(o in approvals and approvals[o]["organization_id"] == o and approvals[o]["decision"] == "approve" and approvals[o]["version"] == draft["version"] and approvals[o]["terms_hash"] == terms_hash(draft) for o in named(draft))
        holds_ok &= dt(event["at"]) < dt(draft["deadline"]) and all(data["holds"].get(o) and all(dt(h["end"]) > dt(event["at"]) for h in data["holds"][o]) for o in named(draft))
    all_holds = defaultdict(list)
    for other in records.all("lot"):
        for owner, hs in other["holds"].items():
            for h in hs:
                resource=h['resource']
                if resource=='lot':
                    resource='lot:'+other['draft']['lot_id']
                    capacities[(owner,resource)]=sum(i['pounds'] for i in other['draft']['items'])
                all_holds[(owner, resource)].append(h)
    booking_ok = True
    for key, hs in all_holds.items():
        capacity = capacities.get(key, 0)
        for h in hs:
            at = dt(h["start"])
            booking_ok &= sum(number(x.get("pounds") or 0) for x in hs if dt(x["start"]) <= at < dt(x["end"])) <= capacity + 1e-8
    totals = defaultdict(float)
    for p in pathways:
        totals[p["produce_id"]] += number(p["pounds"])
    conservation = all(abs(totals[i["produce_id"]] - i["pounds"]) < 1e-6 for i in lot["draft"]["items"])
    # Fair share is a household's whole week: its live pickups from every lot, not only this one.
    pickups = [p for p in records.all("pickup") if p["status"] != "released"]
    received = defaultdict(float)
    for p in pickups:
        received[p["request_code"]] += p["pounds"]
    fairness = all(received[r["request_code"]] + r.get("initial_received_lb", 0) <= r["fair_share_lb"] + 1e-6 for r in records.all("request"))
    failures = [e for e in events if e["kind"] == "number_check_failure"]
    counted = sum(e["data"].get("count", 0) for e in failures) == lot.get("number_check_failures", 0)
    return {"zero_invalid_commitments": approval_ok and holds_ok and booking_ok, "no_double_booking": booking_ok, "pounds_conserved": conservation, "fair_share_respected": fairness, "versioned_approvals": approval_ok, "no_auto_commit": approval_ok and holds_ok, "all_pounds_have_pathway": conservation and all(p.get("status") and p.get("reason") for p in pathways), "number_check_failures_counted": counted}
