"""Changed versions of a committed lot after a disruption (#23 join, Workflow 4).

When a food bank's cooler fails after commitment, that food bank's own agent proposes a
new version of the plan (Lane B's ``cooler_failure_flow.NewVersion`` terms). The core only
records it. It checks the terms against its own records, takes each named organization's
fresh human decision on that exact version and terms hash, and only when every named
organization approved does it place the owners' holds, amend the committed allocations,
and move the affected household pickups to the receiving food bank. Earlier approvals
never carry over, a decline commits nothing, and nothing here decides for an organization
(ADR 0001, 0004). Every number comes from the terms, the records, or a calculator (ADR 0002).

**Proposed**, pending ticket #1: the lot draft (``DraftVersion``) has no transfer between
food banks after delivery, so a change is its own record (kind ``change``) on top of the
committed version instead of a draft amendment.
"""
import copy
from collections import defaultdict
from zoneinfo import ZoneInfo
from harvestnet_agents.negotiation import parse_facts
from harvestnet_agents.profiles import STORAGE_COLD
from harvestnet_agents.terms import terms_hash
from .protocol import Conflict, dt, named, number


def _key(lot_id, version):
    return f'{lot_id}:{version}'


def latest_version(lot):
    return max(lot['draft']['version'], lot.get('change_version', 0))


def find(records, lot_id, version):
    try:
        return records.get('change', _key(lot_id, version))
    except KeyError:
        return None


def changes_for(records, lot_id):
    return sorted((c for c in records.all('change') if c['lot_id'] == lot_id), key=lambda c: c['version'])


def _local(engine, value):
    return dt(value).astimezone(ZoneInfo(engine.fixture['timezone']))


def _held(lot, food_bank_id):
    held = defaultdict(float)
    for a in lot['commitments']:
        if a['food_bank_id'] == food_bank_id and a['pounds'] > 0 and a.get('pathway') is None:
            held[a['produce_id']] += a['pounds']
    return dict(held)


def trip(records, lot, commitment):
    """When this committed pound's trip leaves and arrives, as datetimes, or ``None``.

    A pound a committed change moved travels on that change's own trip; everything else on its
    draft transport to the food bank."""
    if lot.get('change_version') and commitment.get('version') == lot['change_version'] and commitment.get('pathway') is None:
        change = find(records, lot['draft']['lot_id'], lot['change_version'])
        move = next((m for m in change['terms']['moves'] if m['produce_id'] == commitment['produce_id']
                     and m['to_food_bank_id'] == commitment['food_bank_id']), None) if change else None
        if move:
            return dt(move['departs_at']), dt(move['arrives_at'])
    transport = next((t for t in lot['draft']['transports'] if t['food_bank_id'] == commitment['food_bank_id']), None)
    return (dt(transport['departs_at']), dt(transport['arrives_at'])) if transport else None


def holding(engine, lot_id, food_bank_id):
    """The food bank's share of the committed plan, in Lane B's ``holding`` shape. No household data."""
    records = engine.records
    lot = records.get('lot', lot_id)
    if lot['status'] != 'committed':
        raise Conflict('only a committed plan has holdings to protect')
    held = _held(lot, food_bank_id)
    if not held:
        raise Conflict(f'{food_bank_id} holds no committed produce from this lot')
    bank = records.get('bank', food_bank_id)
    upcoming = [w for w in bank['pickup_windows'] if dt(w['end']) > dt(engine.now)]
    if not upcoming:
        raise Conflict('this food bank has no pickup hours left for its households')
    tonight = min(upcoming, key=lambda w: dt(w['start']))
    return {'event_id': lot_id, 'lot_id': lot_id, 'current_version': latest_version(lot),
            'food_bank_id': food_bank_id, 'food_bank_name': engine.names[food_bank_id],
            'timezone': engine.fixture['timezone'],
            'items': [{'produce_id': p, 'pounds': lb} for p, lb in held.items()],
            # When this food bank's households collect next: its own pickup hours, not any household's.
            'households_pickup': {'start': tonight['start'], 'end': tonight['end']},
            # Recorded route data; Lane A has no route calculator beyond arrival_time.
            'travel_minutes': dict(engine.fixture.get('travel_minutes_between_food_banks', {}).get(food_bank_id, {}))}


def _parts(terms):
    try:
        return [list(terms[k]) for k in ('moves', 'fallback', 'staying', 'needs_human_check')]
    except (KeyError, TypeError) as exc:
        raise ValueError('change terms need moves, fallback, staying and needs_human_check lists') from exc


def propose(engine, lot_id, body, owner):
    """Record a food bank's proposed change. Returns the body for Lane C's approval requests."""
    terms, organizations, dashboard = body.get('terms'), body.get('organizations'), body.get('dashboard')
    if not isinstance(terms, dict) or not isinstance(organizations, list) or (dashboard is not None and not isinstance(dashboard, dict)):
        raise ValueError('terms, organizations and an optional dashboard object are required')
    records, calc = engine.records, engine.calc
    with records.transaction():
        lot = records.get('lot', lot_id)
        if lot['status'] != 'committed':
            raise Conflict('only a committed plan can be changed after a disruption')
        if terms.get('event_id') != lot_id or terms.get('lot_id') != lot_id:
            raise ValueError('change terms name a different lot')
        if terms.get('proposer_id') != owner:
            raise ValueError('a food bank proposes changes only to its own holding')
        if terms.get('change') != 'cooler_failure':
            raise ValueError('only cooler-failure changes are supported')
        if (records.get('bank', owner).get('cooler') or {}).get('status') != 'failed':
            raise Conflict("record the failed cooler reading in this food bank's status first")
        latest = latest_version(lot)
        if terms.get('based_on_version') != latest or terms.get('version') != latest + 1:
            raise Conflict('stale version: a change builds on the latest committed version')
        if any(c['status'] == 'awaiting_approvals' for c in changes_for(records, lot_id)):
            raise Conflict('another change of this lot is awaiting approvals')
        moves, fallback, staying, human = _parts(terms)
        accounted = defaultdict(float)
        for part in (moves, fallback, staying, human):
            for x in part:
                accounted[x['produce_id']] += number(x['pounds'])
        held = _held(lot, owner)
        if set(accounted) != set(held) or any(abs(accounted[p] - held[p]) > 1e-6 for p in held):
            raise Conflict('the change does not account for every committed pound at this food bank')
        profiles = calc.profiles
        if not all(profiles.must_move(x['produce_id']) for x in moves + fallback):
            raise Conflict('only cold-dependent produce moves after a cooler failure')
        if not all(profiles.can_stay(x['produce_id']) for x in staying):
            raise Conflict('cold-dependent produce cannot stay in a failed cooler')
        receivers = {m['to_food_bank_id'] for m in moves}
        if any(m['from_food_bank_id'] != owner for m in moves) or len(receivers) > 1 or owner in receivers or not receivers <= set(engine.banks):
            raise ValueError('moves go from the proposing food bank to one other food bank')
        expected = sorted(receivers | {owner})
        if len(set(organizations)) != len(organizations) or sorted(organizations) != expected:
            raise ValueError('exactly the receiving food bank and the proposer approve a cooler-failure change')
        routes = engine.fixture.get('travel_minutes_between_food_banks', {}).get(owner, {})
        for m in moves:
            travel = routes.get(m['to_food_bank_id'])
            if travel is None:
                raise Conflict('no recorded travel time to the receiving food bank')
            if calc.arrival_time(dt(m['departs_at']), travel) != dt(m['arrives_at']):
                raise Conflict('arrival time does not match the recorded route')
            collect = m['households_collect']
            if dt(collect['start']) < dt(m['arrives_at']) or dt(collect['end']) <= dt(collect['start']):
                raise ValueError('households collect only after the produce arrives')
        failure_at = ((terms.get('evidence') or {}).get('cooler_reading') or {}).get('observed_at')
        if not isinstance(failure_at, str):
            raise ValueError("change terms must carry the failed cooler reading's observed_at")
        dt(failure_at)
        version = terms['version']
        change = {'lot_id': lot_id, 'version': version, 'based_on_version': latest, 'proposer_id': owner,
                  'organizations': expected, 'terms': copy.deepcopy(terms), 'terms_hash': terms_hash(terms),
                  'status': 'awaiting_approvals', 'approvals': {}, 'failure_at': failure_at,
                  'proposed_at': engine.now, 'dashboard': copy.deepcopy(dashboard)}
        records.put('change', _key(lot_id, version), change)
        records.event(lot_id, engine.now, 'change_proposed', {'version': version, 'based_on_version': latest,
                      'proposer_id': owner, 'organizations': expected, 'terms_hash': change['terms_hash'], 'change': terms['change']})
    return {'lot_id': lot_id, 'version': version, 'based_on_version': latest, 'status': 'awaiting_approvals',
            'committed': False, 'terms_hash': change['terms_hash'], 'needs_approval_from': expected,
            'approval_request': {'lot_id': lot_id, 'version': version, 'terms': terms, 'organizations': expected}}


def _deadline(change):
    moves = change['terms']['moves']
    return min(dt(m['arrives_at']) for m in moves) if moves else None


def approve(engine, receipt, owner):
    """One organization's human decision on this exact change version and terms hash."""
    if owner != receipt['organization_id']:
        raise ValueError('an organization cannot approve for another')
    if receipt['decision'] not in ('approve', 'decline'):
        raise ValueError('explicit human decision required')
    records, now = engine.records, engine.now
    lot_id, version = receipt['lot_id'], receipt['version']
    with records.transaction():
        rid = receipt.get('receipt_id')
        if rid:
            try:
                previous = records.get('receipt', rid)
            except KeyError:
                pass
            else:
                if previous['receipt'] != receipt:
                    raise Conflict('receipt ID reused with different terms')
                return previous['result']
        change = records.get('change', _key(lot_id, version))
        if change['status'] != 'awaiting_approvals':
            raise Conflict(f"version {version} is {change['status']}; a further change needs a new version")
        if receipt['terms_hash'] != change['terms_hash']:
            raise Conflict('stale version or changed terms')
        if owner not in change['organizations']:
            raise Conflict('unnamed organization')
        deadline = _deadline(change)
        if deadline and dt(now) >= deadline:
            raise Conflict('the planned trip time has passed; propose a new version')
        earlier = change['approvals'].get(owner)
        if earlier and earlier['decision'] != receipt['decision']:
            raise Conflict('decision already recorded; change terms with a fresh version')
        change['approvals'][owner] = copy.deepcopy(receipt)
        records.event(lot_id, now, 'change_decision', receipt)
        if receipt['decision'] == 'decline':
            change.update(status='declined', declined_by=owner)
            records.event(lot_id, now, 'change_declined', {'version': version, 'organization_id': owner})
        waiting = [o for o in change['organizations'] if change['approvals'].get(o, {}).get('decision') != 'approve']
        if not waiting and change['status'] == 'awaiting_approvals':
            _commit(engine, change)
        records.put('change', _key(lot_id, version), change)
        result = {'lot_id': lot_id, 'version': version, 'decision_recorded': True, 'status': change['status'],
                  'approved_by': sorted(o for o, r in change['approvals'].items() if r['decision'] == 'approve'),
                  'waiting_for': waiting if change['status'] == 'awaiting_approvals' else [],
                  'committed': change['status'] == 'committed'}
        if rid:
            records.put('receipt', rid, {'receipt': receipt, 'result': result})
        return result


def _owner_holds(records, owner, resource):
    return [h for lot in records.all('lot') for h in lot['holds'].get(owner, []) if h['resource'] == resource]


def _check_free(records, owner, hold, capacity):
    start, end = dt(hold['start']), dt(hold['end'])
    if start >= end:
        raise Conflict('hold has an empty interval')
    overlapping = [x for x in _owner_holds(records, owner, hold['resource']) + [hold] if dt(x['start']) < end and start < dt(x['end'])]
    for at in {start} | {dt(x['start']) for x in overlapping if start <= dt(x['start']) < end}:
        total = sum(number(x.get('pounds') or 0) for x in overlapping if dt(x['start']) <= at < dt(x['end']))
        if total > max(0.0, capacity) + 1e-8:
            raise Conflict(f"{owner}'s {hold['resource']} would be double booked")


def _commit(engine, change):
    records, calc, now = engine.records, engine.calc, engine.now
    terms, lot_id, version, owner = change['terms'], change['lot_id'], change['version'], change['proposer_id']
    lot = records.get('lot', lot_id)
    moves, fallback = terms['moves'], terms['fallback']
    profiles = calc.profiles
    new_holds = defaultdict(list)
    receiver = moves[0]['to_food_bank_id'] if moves else None
    if moves:
        depart = min(_local(engine, m['departs_at']) for m in moves)
        arrive = max(_local(engine, m['arrives_at']) for m in moves)
        collect_end = max(_local(engine, m['households_collect']['end']) for m in moves)
        pounds = sum(number(m['pounds']) for m in moves)
        cold = sum(number(m['pounds']) for m in moves if profiles.get(m['produce_id']).storage_resource == STORAGE_COLD)
        # The receiver's recorded cold space at arrival, rechecked now, not the agent's answer.
        facts = parse_facts('food_bank', engine.facts(receiver, lot['draft']))
        storage = calc.storage_at(facts.storage, arrive)
        hold = {'resource': STORAGE_COLD, 'pounds': cold, 'start': arrive.isoformat(), 'end': collect_end.isoformat(), 'version': version}
        _check_free(records, receiver, hold, storage.cold_free_lb)
        truck = records.get('bank', owner).get('truck')
        if not truck or pounds > truck['capacity_lb'] + 1e-8 or not (dt(truck['window']['start']) <= depart < arrive <= dt(truck['window']['end'])):
            raise Conflict("the proposing food bank's truck can't make this trip")
        if not truck['refrigerated'] and any(profiles.get(m['produce_id']).transport.cold_required for m in moves):
            raise Conflict('this produce needs a refrigerated truck')
        truck_hold = {'resource': 'truck', 'pounds': pounds, 'start': depart.isoformat(), 'end': arrive.isoformat(), 'version': version}
        _check_free(records, owner, truck_hold, truck['capacity_lb'])
        new_holds[receiver].append(hold)
        new_holds[owner].append(truck_hold)
    # From the failure on, the failed cooler holds nothing cold.
    failure = _local(engine, change['failure_at'])
    kept = []
    for h in lot['holds'].get(owner, []):
        if h['resource'] != STORAGE_COLD:
            kept.append(h)
        elif dt(h['start']) < failure:
            kept.append({**h, 'end': min(dt(h['end']), failure).isoformat()})
    lot['holds'][owner] = kept
    for org, hs in new_holds.items():
        lot['holds'].setdefault(org, []).extend(hs)

    moved = defaultdict(float)
    for m in moves:
        moved[m['produce_id']] += number(m['pounds'])
    touched = set(moved) | {f['produce_id'] for f in fallback}
    commitments = [a for a in lot['commitments'] if not (a['food_bank_id'] == owner and a['produce_id'] in touched and a.get('pathway') is None)]
    commitments += [{'produce_id': p, 'food_bank_id': receiver, 'pounds': lb, 'version': version} for p, lb in moved.items()]
    commitments += [{'produce_id': f['produce_id'], 'food_bank_id': owner, 'pounds': number(f['pounds']), 'version': version,
                     'pathway': f['kind'], 'pathway_reason': f['reason']} for f in fallback]
    lot.update(commitments=commitments, change_version=version)

    moved_pickups, kept_same_day, released = _move_pickups(engine, lot, change, receiver, moved, fallback, touched)
    change.update(status='committed', committed_at=now, holds=dict(new_holds), moved_pickups=moved_pickups,
                  kept_same_day=kept_same_day, released_pickups=released)
    records.put('lot', lot_id, lot)
    records.event(lot_id, now, 'change_commitment', {'version': version, 'terms_hash': change['terms_hash'],
                  'approvals': change['approvals'], 'holds': dict(new_holds), 'moved_pickups': moved_pickups})


def _move_pickups(engine, lot, change, receiver, moved, fallback, touched):
    """Re-point committed pickups of moved produce to the receiver, within the new version's terms."""
    records, now, version, owner = engine.records, engine.now, change['version'], change['proposer_id']
    budget = dict(moved)
    same_day = defaultdict(float)
    for f in fallback:
        if f['kind'] == 'same_day_offer':
            same_day[f['produce_id']] += number(f['pounds'])
    rbank = records.get('bank', receiver) if receiver else None
    moved_ids, kept, released = [], [], []
    for p in sorted(records.all('pickup'), key=lambda p: p['pickup_id']):
        if p['lot_id'] != lot['draft']['lot_id'] or p['food_bank_id'] != owner or p['status'] != 'committed':
            continue
        pid = p['items'][0]['produce_id']
        if pid not in touched:
            continue
        window = None
        if receiver and budget.get(pid, 0) + 1e-8 >= p['pounds']:
            m = next(m for m in change['terms']['moves'] if m['produce_id'] == pid)
            collect = {k: _local(engine, m['households_collect'][k]).isoformat() for k in ('start', 'end')}
            request = records.get('request', p['request_code'])
            original = next(i for i in lot['draft']['items'] if i['produce_id'] == pid)
            # The household's own pickup times and limits still apply at the new food bank.
            window = engine.eligible({**request, 'chosen_food_bank_ids': [receiver]}, {**rbank, 'pickup_windows': [collect]},
                                     original, _local(engine, m['arrives_at']))
        if window:
            budget[pid] -= p['pounds']
            p.update(food_bank_id=receiver, food_bank_name=engine.names[receiver], window=window, version=version,
                     moved_from_food_bank_id=owner, reply_expected=receiver not in request.get('chosen_food_bank_ids', []))
            records.put('pickup', p['pickup_id'], p)
            records.event(p['lot_id'], now, 'pickup_notice', p)
            moved_ids.append(p['pickup_id'])
        elif same_day.get(pid, 0) + 1e-8 >= p['pounds']:
            same_day[pid] -= p['pounds']
            kept.append(p['pickup_id'])
        else:
            p.update(status='released', release_reason='cooler failure: no safe pathway for this portion')
            records.put('pickup', p['pickup_id'], p)
            records.event(p['lot_id'], now, 'pickup_released', {'pickup_id': p['pickup_id'], 'pounds': p['pounds'], 'reason': p['release_reason']})
            released.append(p['pickup_id'])
    return moved_ids, kept, released


def pathways(engine, lot_id):
    out = []
    for p in engine.pathways(lot_id):
        kind, reason = p.pop('pathway', None), p.pop('pathway_reason', None)
        if kind:
            p.update(status=kind, reason=reason)
        elif p.get('version') and p['version'] > engine.records.get('lot', lot_id)['draft']['version']:
            p['reason'] = 'Fresh exact-version approvals of the changed plan and owner holds'
        out.append(p)
    return out


def rule_checks(engine, lot_id):
    """The core's rule checks over the lot after its changes, plus checks on each change."""
    from .checks import rule_checks as core_checks
    records = engine.records
    lot = records.get('lot', lot_id)
    orgs = set(named(lot['draft'])) | {o for c in changes_for(records, lot_id) for o in c['organizations']}
    caps = {(o, r): v for o in orgs for r, v in engine.capacities(o, lot['draft']).items()}
    core = core_checks(records, lot_id, pathways(engine, lot_id), caps)
    change = change_checks(engine, lot_id)
    merged = {k: core[k] and change.get(k, True) for k in core}
    merged.update({k: v for k, v in change.items() if k not in core})
    return merged


def change_checks(engine, lot_id):
    """Recomputed from stored terms, decisions, holds and pickups, never from a status flag."""
    records, profiles = engine.records, engine.calc.profiles
    lot = records.get('lot', lot_id)
    events = records.events(lot_id)
    versioned = commits = cold = failed = pickups = True
    for c in changes_for(records, lot_id):
        terms, digest, v = c['terms'], terms_hash(c['terms']), c['version']
        moves = terms['moves']
        commit_events = [e for e in events if e['kind'] == 'change_commitment' and e['data']['version'] == v]
        cold &= all(profiles.must_move(x['produce_id']) for x in moves + terms['fallback'])
        cold &= all(profiles.can_stay(x['produce_id']) for x in terms['staying'])
        if c['status'] != 'committed':
            commits &= not commit_events
            continue
        approvals = c['approvals']
        versioned &= digest == c['terms_hash'] and terms['version'] == c['based_on_version'] + 1 and all(
            approvals.get(o, {}).get('decision') == 'approve' and approvals[o]['organization_id'] == o
            and approvals[o]['version'] == v and approvals[o]['terms_hash'] == digest for o in c['organizations'])
        decisions = [e for e in events if e['kind'] == 'change_decision' and e['data']['version'] == v
                     and e['data']['decision'] == 'approve' and e['data']['terms_hash'] == digest]
        holders = {c['proposer_id'], moves[0]['to_food_bank_id']} if moves else set()
        commits &= len(commit_events) == 1 and set(c['organizations']) <= {e['data']['organization_id'] for e in decisions} \
            and all(e['sequence'] < commit_events[0]['sequence'] for e in decisions) \
            and all(commit_events[0]['data']['holds'].get(o) for o in holders)
        failure = dt(c['failure_at'])
        failed &= all(dt(h['end']) <= failure for h in lot['holds'].get(c['proposer_id'], []) if h['resource'] == STORAGE_COLD)
        for pid in c.get('moved_pickups', []):
            p = records.get('pickup', pid)
            m = next(m for m in moves if m['produce_id'] == p['items'][0]['produce_id'])
            w = m['households_collect']
            pickups &= p['version'] >= v and p['food_bank_id'] == m['to_food_bank_id'] \
                and dt(w['start']) <= dt(p['window']['start']) < dt(p['window']['end']) <= dt(w['end'])
    failed &= not cold_left_in_failed_cooler(engine, lot_id)
    return {'versioned_approvals': versioned, 'no_auto_commit': commits, 'only_cold_dependent_items_move': cold,
            'failed_cooler_holds_nothing_cold': failed, 'household_pickups_follow_new_version': pickups}


def failed_coolers(engine):
    """Food banks whose own recorded status says the cooler failed."""
    return [bid for bid in engine.banks if (engine.records.get('bank', bid).get('cooler') or {}).get('status') == 'failed']


def cold_left_in_failed_cooler(engine, lot_id):
    """Cold produce still committed to a food bank whose cooler failed, and not accounted for.

    Recomputed from the lot's current commitments, not from any change's status. A committed
    pound there is accepted only when a human holds it and it is labeled: the lot's
    ``held_for_human`` covers its pounds, and no cold pickup there is still scheduled. Produce an
    approved change moved is no longer a commitment at that food bank. Returns the problems."""
    records, profiles = engine.records, engine.calc.profiles
    lot = records.get('lot', lot_id)
    problems = []
    for bid in failed_coolers(engine):
        scheduled = [p for p in records.all('pickup') if p['lot_id'] == lot_id and p['food_bank_id'] == bid and p['status'] == 'committed'
                     and any(profiles.must_move(i['produce_id']) for i in p['items'])]
        if scheduled:
            problems.append(f"cold pickups still scheduled at {bid}'s failed cooler: {sorted(p['pickup_id'] for p in scheduled)}")
        for a in lot['commitments']:
            if a['food_bank_id'] != bid or a['pounds'] <= 0 or a.get('pathway') is not None or not profiles.must_move(a['produce_id']):
                continue
            labeled = sum(h['pounds'] for h in lot.get('held_for_human', []) if h['food_bank_id'] == bid and h['produce_id'] == a['produce_id'] and h.get('reason'))
            if labeled + 1e-6 < a['pounds']:
                problems.append(f"{a['pounds']} lb of {a['produce_id']} is committed to {bid}'s failed cooler and neither moved nor held for a human")
    return problems


def decision_records(change):
    """Lane C-shaped decision records for Lane B's ``approval_status``."""
    return [{'event_id': change['lot_id'], 'version': a['version'], 'organization_id': a['organization_id'],
             'terms_hash': a['terms_hash'], 'decision': a['decision']} for a in change['approvals'].values()]


def households(engine, lot_id, version):
    """Request records for the households whose pickups this version moved (Lane B's shape)."""
    records = engine.records
    grouped = {}
    for p in sorted(records.all('pickup'), key=lambda p: p['pickup_id']):
        if p['lot_id'] != lot_id or p.get('version') != version or not p.get('moved_from_food_bank_id') or p['status'] != 'committed':
            continue
        r = records.get('request', p['request_code'])
        h = grouped.setdefault(p['request_code'], {'request_code': p['request_code'], 'language': r['language'],
                                                   'chosen_food_banks': list(r.get('chosen_food_bank_ids', [])), 'portions': [], 'pickup_ids': []})
        h['portions'] += [{'produce_id': i['produce_id'], 'pounds': i['pounds'], 'food_bank_id': p['food_bank_id']} for i in p['items']]
        h['pickup_ids'].append(p['pickup_id'])
    return list(grouped.values())


def summaries(records, food_bank_id):
    """Changes this food bank proposed or must approve, with the proposer's reason cards. No household data."""
    out = []
    for c in sorted(records.all('change'), key=lambda c: (c['lot_id'], c['version'])):
        if food_bank_id != c['proposer_id'] and food_bank_id not in c['organizations']:
            continue
        out.append({'lot_id': c['lot_id'], 'version': c['version'], 'based_on_version': c['based_on_version'],
                    'change': c['terms']['change'], 'status': c['status'], 'proposer_id': c['proposer_id'],
                    'needs_approval_from': c['organizations'],
                    'approved_by': sorted(o for o, a in c['approvals'].items() if a['decision'] == 'approve'),
                    'declined_by': sorted(o for o, a in c['approvals'].items() if a['decision'] == 'decline'),
                    'needs_your_approval': c['status'] == 'awaiting_approvals' and food_bank_id in c['organizations'] and food_bank_id not in c['approvals'],
                    'dashboard': c['dashboard']})
    return out


def pending_approvals(records, owner):
    out = []
    for c in records.all('change'):
        if c['status'] != 'awaiting_approvals' or owner not in c['organizations'] or owner in c['approvals']:
            continue
        deadline = _deadline(c)
        out.append({'lot_id': c['lot_id'], 'version': c['version'], 'terms_hash': c['terms_hash'], 'requested_at': c['proposed_at'],
                    'expires_at': deadline.isoformat() if deadline else None,
                    'why_you': ['proposing_food_bank' if owner == c['proposer_id'] else 'receiving_food_bank'],
                    'summary': c['terms']['reason'], 'terms': c['terms'], 'status': 'awaiting_decision', 'change': c['terms']['change']})
    return out
