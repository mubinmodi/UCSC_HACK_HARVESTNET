"""Lane B's rule checks over a scenario run's event log (ticket #20).

Each check reads only the plain JSON event log (``scenario_runner.EventLog``), so it can
run on a saved log, and on Lane A's harness log once it carries the same event kinds.
The names don't overlap with the fixture's (Lane A's, #7) rule checks, so the two sets
merge as ``{**lane_a_checks, **lane_b_checks}``:

- ``no_central_decider`` (ADR 0001): every move is the mover's own, on its own turn, in
  its own role, from its own facts (never another organization's, never a household's
  request code); a food bank's counter changes only its own share, except a contest or
  take-back that shifts one item from one other food bank to itself, within its own
  fair-share gap (ADR 0013); every hold is on the
  mover's own resources; every approval is that organization's own human's; every new
  version comes from one organization's counter.
- ``every_move_has_reason``: every move, version, and stop has a non-empty reason.
- ``advocate_never_votes``: the advocate only counters or passes, and never holds,
  approves, or is named in a version.
- ``numbers_trace_to_inputs`` (ADR 0002): every number and time in a move (reason,
  amendment, holds) is in the version it's about, the draft's own totals, the mover's
  facts, its turn, or a calculator result from that same move. Facts' fair-share gaps
  and the offer's pounds trace to calculator calls too.
- ``commits_only_with_every_named_approval`` (ADR 0001): a commitment is on the current
  version, after every named organization's human approved that exact version and terms
  hash, with every named organization's holds, before the deadline and before any hold
  ends; at most one per lot; no move commits.
- ``cold_dependent_produce_follows_profiles`` (ADR 0003): in every agreed or committed
  version, every item has a produce profile, cold-dependent produce goes only where cold
  storage at arrival holds it, and cold-chain produce travels only in a refrigerated
  vehicle; after a cooler failure, only cold-dependent produce is moved.

The cold checks read the profile fields (``needs_cold``, ``transport.cold_required``),
never crop names, and use the recorded facts directly rather than calculators, so they
check the calculators' answers instead of repeating them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from .llm_negotiators import NumberPool, text_number_problems
from .negotiation import (
    POUNDS_TOLERANCE,
    DraftError,
    DraftVersion,
    Mover,
    amendment_from_dict,
    contest_of,
    food_bank_amendment_problem,
    parse_draft,
)
from .profiles import ProfileSet, load_profiles

__all__ = ["LANE_B_RULE_CHECKS", "RuleCheckResult", "run_lane_b_rule_checks"]

Event = Mapping[str, Any]
# The advocate gets pooled counts and the shared records of declines and contests, nothing else.
ADVOCATE_FACT_FIELDS = frozenset({"gaps", "declined", "contests"})


@dataclass(frozen=True)
class RuleCheckResult:
    name: str
    passed: bool
    failures: tuple[str, ...] = field(default=())


def run_lane_b_rule_checks(events: Sequence[Event], profiles: ProfileSet | None = None) -> dict[str, RuleCheckResult]:
    """Run every Lane B rule check over an event log."""
    log = _Log(events, profiles or load_profiles())
    out = {}
    for name, check in LANE_B_RULE_CHECKS.items():
        failures = tuple(check(log))
        out[name] = RuleCheckResult(name, not failures, failures)
    return out


class _Log:
    def __init__(self, events: Sequence[Event], profiles: ProfileSet):
        self.events = list(events)
        self.profiles = profiles
        self.by_seq = {e["seq"]: e for e in self.events}
        scenario = next((e for e in self.events if e["kind"] == "scenario"), {})
        self.roles = {o["organization_id"]: o["role"] for o in scenario.get("organizations", [])}
        self.request_codes = list(scenario.get("request_codes", []))
        self.versions = {(e["lot_id"], e["version"]): e for e in self.events if e["kind"] == "version"}

    def of(self, kind: str) -> list[Event]:
        return [e for e in self.events if e["kind"] == kind]

    def draft(self, lot_id: str, version: int) -> DraftVersion:
        return parse_draft(self.versions[(lot_id, version)]["terms"])

    def outputs(self, seqs: Sequence[int]) -> list[Any]:
        return [self.by_seq[s].get("output") for s in seqs if s in self.by_seq]

    def latest_facts(self, organization_id: str, before_seq: int) -> Mapping[str, Any] | None:
        found = None
        for e in self.events:
            if e["seq"] >= before_seq:
                break
            if e["kind"] == "facts" and e["organization_id"] == organization_id:
                found = e["facts"]
        return found

    def needs_cold(self, produce_id: str) -> bool | None:
        return self.profiles.get(produce_id).needs_cold if produce_id in self.profiles else None


# --- The checks ---------------------------------------------------------------------------


def no_central_decider(log: _Log) -> list[str]:
    out = []
    for e in log.of("move"):
        org, move, turn = e["organization_id"], e["move"], e["turn"]
        where = f"move {e['seq']} ({org})"
        if move["organization_id"] != org or turn["organization_id"] != org:
            out.append(f"{where}: the move is {move['organization_id']}'s on {turn['organization_id']}'s turn")
        if log.roles.get(org) != e["role"]:
            out.append(f"{where}: role {e['role']}, but {org} is a {log.roles.get(org)}")
        if not e.get("negotiator"):
            out.append(f"{where}: no negotiator named, so it may not be the organization's own")
        out.extend(f"{where}: {p}" for p in _facts_problems(org, e["role"], e["facts"], log.request_codes))
        if e["role"] == "food_bank" and "amendment" in move:
            out.extend(f"{where}: {p}" for p in _food_bank_counter_problems(org, move["amendment"], e, log))
        if move.get("holds") and move.get("resource_owner") != org:
            out.append(f"{where}: holds another organization's resources")
    for e in log.of("facts"):
        out.extend(f"facts {e['seq']} ({e['organization_id']}): {p}"
                   for p in _facts_problems(e["organization_id"], e["role"], e["facts"], log.request_codes))
    for h in log.of("hold"):
        if h["owner_id"] != h["organization_id"]:
            out.append(f"hold {h['seq']}: {h['organization_id']} holds {h['owner_id']}'s resource")
    for a in log.of("approval"):
        if a.get("source") != "scripted_human" and a.get("source") != "human":
            out.append(f"approval {a['seq']}: not from {a['organization_id']}'s own human ({a.get('source')})")
        named = log.versions.get((a["lot_id"], a["version"]), {}).get("named_organizations", [])
        if a["organization_id"] not in named:
            out.append(f"approval {a['seq']}: {a['organization_id']} is not named in version {a['version']}")
    for v in log.of("version"):
        if v["version"] == 1:
            continue
        m = log.by_seq.get(v.get("move_seq"))
        if m is None or m["kind"] != "move" or m["move"]["action"] != "counter" or m["organization_id"] != v["proposer_id"]:
            out.append(f"version {v['version']}: not created by its proposer's own counter")
        elif m["version"] != v["based_on_version"]:
            out.append(f"version {v['version']}: based on {v['based_on_version']}, but the counter was about {m['version']}")
    return out


def _food_bank_counter_problems(org: str, raw: Mapping[str, Any], e: Event, log: _Log) -> list[str]:
    """A food bank's counter changes only its own share, except in exactly one shape: a contest
    (or take-back) shifting one item from one other food bank to itself (ADR 0013), and then no
    further than its own fair-share gap under the version it's about, from its own facts."""
    try:
        amendment = amendment_from_dict(raw)
    except (DraftError, KeyError, TypeError, ValueError) as exc:
        return [f"a food bank's counter has an unreadable amendment ({exc})"]
    problem = food_bank_amendment_problem(org, amendment)
    if problem is not None:
        return [problem]
    contest = contest_of(org, amendment)
    terms = log.versions.get((e["lot_id"], e["version"]), {}).get("terms")
    gap = (e.get("facts") or {}).get("demand", {}).get("below_fair_share_lb")
    if contest is None or terms is None or gap is None:
        return []
    remaining = gap - parse_draft(terms).planned_lb(org)
    if contest.pounds > remaining + POUNDS_TOLERANCE:
        return [f"its contest moves {contest.pounds:g} lb of {contest.produce_id} from {contest.from_food_bank_id}, more than "
                f"its own remaining fair-share gap of {max(0.0, remaining):g} lb (ADR 0013)"]
    return []


def _facts_problems(org: str, role: str, facts: Mapping[str, Any], request_codes: Sequence[str]) -> list[str]:
    out = []
    if role == "donor" and facts.get("donor_id") != org:
        out.append(f"given the donor facts of {facts.get('donor_id')}")
    if role == "food_bank" and facts.get("food_bank_id") != org:
        out.append(f"given the food bank facts of {facts.get('food_bank_id')}")
    if role == "advocate" and (set(facts) - ADVOCATE_FACT_FIELDS):
        out.append(f"the advocate got more than counts: {sorted(set(facts) - ADVOCATE_FACT_FIELDS)}")
    text = json.dumps(facts)
    leaked = [c for c in request_codes if c in text]
    if leaked:
        out.append(f"facts name households' request codes {leaked}")
    return out


def every_move_has_reason(log: _Log) -> list[str]:
    out = []
    for e in log.of("move"):
        if not str(e["move"].get("reason", "")).strip():
            out.append(f"move {e['seq']} ({e['organization_id']}) has no reason")
    for e in log.of("version"):
        if not str(e.get("reason", "")).strip():
            out.append(f"version {e['version']} has no reason")
    for e in log.of("stop"):
        if not str(e.get("reason", "")).strip():
            out.append(f"stop {e['seq']} ({e.get('rule')}) has no reason")
    return out


def advocate_never_votes(log: _Log) -> list[str]:
    advocates = {o for o, r in log.roles.items() if r == "advocate"}
    out = []
    for e in log.of("move"):
        if (e["role"] == "advocate" or e["organization_id"] in advocates) and e["move"]["action"] not in ("counter", "pass"):
            out.append(f"move {e['seq']}: the advocate {e['move']['action']}s")
    for kind in ("hold", "approval", "no_approval"):
        for e in log.of(kind):
            if e["organization_id"] in advocates:
                out.append(f"{kind} {e['seq']}: by the advocate")
    for v in log.of("version"):
        if advocates & set(v.get("named_organizations", [])):
            out.append(f"version {v['version']} names the advocate as a party")
    return out


def numbers_trace_to_inputs(log: _Log) -> list[str]:
    out = []
    for e in log.of("move"):
        terms = log.versions.get((e["lot_id"], e["version"]), {}).get("terms")
        if terms is None:
            out.append(f"move {e['seq']}: version {e['version']} is not in the log")
            continue
        pool = NumberPool()
        for source in (terms, e["facts"], e["turn"], log.outputs(e["calculator_call_seqs"])):
            pool.add(source)
        pool.add(_draft_totals(parse_draft(terms), log), ("draft_totals_lb",))  # pounds, by construction
        out.extend(f"move {e['seq']} ({e['organization_id']}): {p}" for p in _move_number_problems(e["move"], pool))
    for e in log.of("facts"):
        outputs = log.outputs(e["calculator_call_seqs"])
        gaps = {o.get("gap_lb") for o in outputs if isinstance(o, dict)}
        f = e["facts"]
        claimed = [f["demand"]["below_fair_share_lb"]] if "demand" in f else [g["below_fair_share_lb"] for g in f.get("gaps", [])]
        for lb in claimed:
            if lb not in gaps:
                out.append(f"facts {e['seq']} ({e['organization_id']}): {lb} lb below fair share is not a fair-share gap calculator result")
    for v in log.of("version"):
        if v["version"] != 1:
            continue
        pounds = {o.get("pounds") for o in log.outputs(v.get("calculator_call_seqs", [])) if isinstance(o, dict)}
        for item in v["terms"]["items"]:
            if item["pounds"] not in pounds:
                out.append(f"version 1: {item['produce_id']} {item['pounds']} lb is not a unit calculator result")
        pool = NumberPool()
        pool.add(v["terms"])
        out.extend(f"version 1 reason: {p}" for p in text_number_problems(v["reason"], pool))
    return out


def _move_number_problems(move: Mapping[str, Any], pool: NumberPool) -> list[str]:
    problems = text_number_problems(move.get("reason", ""), pool)
    a = move.get("amendment") or {}
    if a.get("pounds") is not None and not pool.has_number(a["pounds"]):
        problems.append(f"the amendment's {a['pounds']:g} lb is not in the inputs or a calculator result")
    for name in ("departs_at", "arrives_at"):
        if a.get(name) and datetime.fromisoformat(a[name]) not in pool.datetimes:
            problems.append(f"the amendment's {name} {a[name]} is not a recorded or calculated time")
    for h in move.get("holds", []):
        if h.get("pounds") is not None and not pool.has_number(h["pounds"]):
            problems.append(f"the hold's {h['pounds']:g} lb is not in the inputs or a calculator result")
        for name in ("start", "end"):
            if datetime.fromisoformat(h[name]) not in pool.datetimes:
                problems.append(f"the hold's {name} {h[name]} is not a recorded or calculated time")
    return problems


def _draft_totals(draft: DraftVersion, log: _Log) -> list[float]:
    """The draft's own totals: sums of its lines (the same totals the LLM negotiators get)."""
    out = []
    for item in draft.items:
        out += [draft.allocated_lb(item.produce_id), draft.unallocated_lb(item.produce_id)]
    banks = draft.named_food_banks()
    for fb in banks:
        lines = draft.allocations_to(fb)
        out += [draft.planned_lb(fb),
                sum(a.pounds for a in lines if log.needs_cold(a.produce_id) is not False),
                sum(a.pounds for a in lines if log.needs_cold(a.produce_id) is False)]
    out.append(sum(draft.planned_lb(fb) for fb in banks))
    donor_moved = [fb for fb in banks if (tr := draft.transport(fb)) is not None and tr.mover is Mover.DONOR]
    load = sum(draft.planned_lb(fb) for fb in donor_moved)
    out.append(load)
    out += [load + draft.planned_lb(fb) for fb in banks if fb not in donor_moved]
    return out


def commits_only_with_every_named_approval(log: _Log) -> list[str]:
    out = []
    for e in log.of("move"):
        if e.get("commits") is not False:
            out.append(f"move {e['seq']} ({e['organization_id']}) is marked as committing")
    commitments = log.of("commitment")
    lots = [c["lot_id"] for c in commitments]
    for lot in set(lots):
        if lots.count(lot) > 1:
            out.append(f"{lot} has {lots.count(lot)} commitments")
    for c in commitments:
        where = f"commitment {c['seq']} (version {c['version']})"
        v = log.versions.get((c["lot_id"], c["version"]))
        if v is None:
            out.append(f"{where}: no such version")
            continue
        later = [w for w in log.of("version") if w["lot_id"] == c["lot_id"] and w["seq"] < c["seq"] and w["version"] > c["version"]]
        if later:
            out.append(f"{where}: not the current version (version {later[-1]['version']} came after it)")
        if c["terms_hash"] != v["terms_hash"]:
            out.append(f"{where}: terms hash differs from the version's")
        at = datetime.fromisoformat(c["at"])
        for org in v["named_organizations"]:
            ok = [a for a in log.of("approval")
                  if a["lot_id"] == c["lot_id"] and a["version"] == c["version"] and a["organization_id"] == org
                  and a["terms_hash"] == v["terms_hash"] and a["decision"] == "approve" and a["seq"] < c["seq"]
                  and datetime.fromisoformat(a["at"]) <= at]
            if not ok:
                out.append(f"{where}: no approval from {org}'s human on this exact version before it")
            holds = [h for h in log.of("hold") if h["lot_id"] == c["lot_id"] and h["version"] == c["version"] and h["organization_id"] == org]
            if not holds:
                out.append(f"{where}: {org} holds nothing on this version")
        declines = [a for a in log.of("approval") if a["lot_id"] == c["lot_id"] and a["version"] == c["version"] and a["decision"] != "approve"]
        if declines:
            out.append(f"{where}: committed although {declines[0]['organization_id']} declined it")
        deadline = datetime.fromisoformat(v["terms"]["deadline"])
        if at > deadline:
            out.append(f"{where}: committed at {c['at']}, after the {v['terms']['deadline']} deadline")
        for h in log.of("hold"):
            if h["lot_id"] == c["lot_id"] and h["version"] == c["version"] and datetime.fromisoformat(h["end"]) < at:
                out.append(f"{where}: {h['organization_id']}'s {h['resource']} hold ended at {h['end']}, before the commitment")
    return out


def cold_dependent_produce_follows_profiles(log: _Log) -> list[str]:
    out = []
    agreed = {(e["lot_id"], e["version"], e["seq"]) for e in log.of("held")} | {(e["lot_id"], e["version"], e["seq"]) for e in log.of("commitment")}
    for lot, version, seq in sorted(agreed, key=lambda x: x[2]):
        draft = log.draft(lot, version)
        donor = log.latest_facts(draft.donor_id, seq) or {}
        for fb in draft.named_food_banks():
            where = f"version {version}, {fb}"
            facts = log.latest_facts(fb, seq) or {}
            lines = draft.allocations_to(fb)
            unknown = [a.produce_id for a in lines if a.produce_id not in log.profiles]
            if unknown:
                out.append(f"{where}: {unknown} has no produce profile, so it can't be allocated")
            cold = [a for a in lines if log.needs_cold(a.produce_id)]
            if not cold:
                continue
            tr = draft.transport(fb)
            if tr is None:
                out.append(f"{where}: cold-dependent produce with no transport line")
                continue
            free = _cold_free_at(facts.get("storage", []), tr.arrives_at)
            needed = sum(a.pounds for a in cold)
            if free < needed:
                out.append(f"{where}: {needed:g} lb cold-dependent produce, {free:g} lb cold space free at arrival")
            chain = [a.produce_id for a in cold if log.profiles.get(a.produce_id).transport.cold_required]
            if chain:
                if tr.mover is Mover.DONOR:
                    refrigerated = bool(draft.drop_off_refrigerated) and bool((donor.get("drop_off") or {}).get("refrigerated"))
                else:
                    refrigerated = bool((facts.get("truck") or {}).get("refrigerated"))
                if not refrigerated:
                    out.append(f"{where}: {chain} needs a cold chain, but the {tr.mover.value}'s vehicle isn't refrigerated")
    for e in log.of("cooler_failure_assessment"):
        for i in e["items_to_move"]:
            if not log.needs_cold(i["produce_id"]):
                out.append(f"cooler failure {e['seq']}: moves {i['produce_id']}, which its profile says doesn't depend on cold")
        for i in e["items_staying"]:
            if log.needs_cold(i["produce_id"]) is not False:
                out.append(f"cooler failure {e['seq']}: leaves cold-dependent {i['produce_id']} in a failed cooler")
    return out


def _cold_free_at(storage: Sequence[Mapping[str, Any]], at: datetime) -> float:
    for s in storage:
        if datetime.fromisoformat(s["window"]["start"]) <= at < datetime.fromisoformat(s["window"]["end"]):
            return float(s["cold_free_lb"])
    return 0.0  # no record for that moment: no space is assumed


LANE_B_RULE_CHECKS: Mapping[str, Callable[[_Log], list[str]]] = {
    "no_central_decider": no_central_decider,
    "every_move_has_reason": every_move_has_reason,
    "advocate_never_votes": advocate_never_votes,
    "numbers_trace_to_inputs": numbers_trace_to_inputs,
    "commits_only_with_every_named_approval": commits_only_with_every_named_approval,
    "cold_dependent_produce_follows_profiles": cold_dependent_produce_follows_profiles,
}
