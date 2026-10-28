"""Schedule real owner moves for public offers, without scripted human decisions."""
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from .protocol import Conflict,named

TEMPLATE_REASON='Validated deterministic owner fallback; human approval is still required.'


def count_number_failure(engine,lot_id,org,problems):
    """Record one failed outgoing-message number check and add it to the lot's count."""
    with engine.records.transaction():
        engine.records.event(lot_id,engine.now,'number_check_failure',{'count':1,'organization_id':org,'problems':problems})
        current=engine.records.get('lot',lot_id)
        current['number_check_failures']=current.get('number_check_failures',0)+1
        engine.records.put('lot',lot_id,current)


def checked_move(engine,lot_id,org,move,pool,reask,fallback):
    """The outgoing-message number check (#8): re-ask the same owner once after a failure,
    and use the deterministic owner move with template wording only after the second
    failure. Every failure is counted."""
    from harvestnet_agents.llm_negotiators import text_number_problems
    for attempt in (1,2):
        problems=text_number_problems(move.get('reason',''),pool)
        if not problems:
            return move
        count_number_failure(engine,lot_id,org,problems)
        if attempt==1:
            move=reask()
    move=fallback()
    move['reason']=TEMPLATE_REASON
    engine.records.event(lot_id,engine.now,'template_fallback',{'organization_id':org,'after_failures':2})
    return move


def declined_by(lot):
    """Organizations whose human declined the lot's current version (approvals reset with each new version)."""
    return sorted(o for o,r in lot['approvals'].items() if r['decision']=='decline')


def cycle_key(draft,position):
    """A version's terms without its numbering, proposer and reason, with the turn-order
    position of whoever made them: the same key twice is a cycle of counters (the agents
    runner's ``counter_cycle`` rule), kept as a preserved disagreement (ADR 0013)."""
    from harvestnet_agents.terms import terms_hash
    terms={k:v for k,v in draft.items() if k not in ('version','based_on_version','proposer_id','reason')}
    return terms_hash(terms),position


def claims_in(engine,lot_id):
    """Every contest or take-back in the lot's shared records, oldest first, with the gap it
    stated: a food bank's counter that moved one item from another food bank to itself (ADR
    0013). Every negotiator reads them, so the other food bank can weigh the claim."""
    out=[]
    for e in engine.records.events(lot_id):
        if e['kind']!='amendment':
            continue
        a,org=e['data'].get('amendment') or {},e['data'].get('organization_id')
        if a.get('kind')=='shift_pounds' and engine.roles.get(org)=='food_bank' and a.get('to_food_bank_id')==org and a.get('from_food_bank_id')!=org:
            out.append({'food_bank_id':org,'from_food_bank_id':a['from_food_bank_id'],'produce_id':a['produce_id'],
                        'gap_lb':a.get('claimant_gap_lb'),'version':e['data']['draft']['version']})
    return out


def contests_in(engine,lot_id):
    """Each pair of food banks contesting an item, once: what the advocate's facts carry."""
    out=[]
    for c in claims_in(engine,lot_id):
        pair={'food_bank_id':c['food_bank_id'],'from_food_bank_id':c['from_food_bank_id'],'produce_id':c['produce_id']}
        if pair not in out: out.append(pair)
    return out


def negotiate_pending(engine,lot_id,provider=None):
    accepts=set()
    no_change=0
    previous_version=None
    seen_terms={}
    cycle=None
    for turn in range(1,201):
        lot=engine.records.get('lot',lot_id)
        d=lot['draft']
        if lot['status']=='committed': return lot
        org=engine.fixture['turn_order'][(turn-1)%len(engine.fixture['turn_order'])]
        if (turn-1)%len(engine.fixture['turn_order'])==0: previous_version=d['version']
        raw={'role':engine.roles[org],'draft':d,'facts':engine.facts(org,d,(),contests_in(engine,lot_id)),'turn':{'organization_id':org,'number':turn,'now':engine.now,'accepted_by':sorted(accepts)},'claims':claims_in(engine,lot_id)}
        role,typed=parse_agent_input(raw)
        from harvestnet_agents.llm_negotiators import NumberPool,precompute
        pool=NumberPool();pool.add(typed);call_start=len(engine.calc.calls)
        pool.add(precompute(role,typed,engine.calc))
        def ask():
            return provider(org,{**raw,'turn':org,'turn_context':raw['turn'],'policy_session':engine.policy_session}) if provider else engine.rules_for(role,org).move(typed).to_dict()
        move=ask()
        for call in engine.calc.calls[call_start:]: pool.add(call.result)
        move=checked_move(engine,lot_id,org,move,pool,ask,lambda:engine.rules_for(role,org).move(typed).to_dict())
        with engine.records.transaction():
            # Take the queued counter in the same transaction that reads it: it is used once.
            try:
                queued=engine.records.get('queued_move',lot_id+':'+org)
            except KeyError:
                queued=None
            else:
                engine.records.delete('queued_move',lot_id+':'+org)
        if queued and queued['version']==d['version']: move={k:v for k,v in queued.items() if k!='lot_id'}
        if move['organization_id']!=org or move['version']!=d['version']:
            raise ValueError('owner move does not match published turn')
        if org=='advocate' and move['action'] not in ('counter','pass'):
            raise ValueError('advocate cannot vote')
        engine.records.event(lot_id,engine.now,'move',move)
        if move['action']=='counter':
            updated=engine.protocol.amend(lot_id,d['version'],org,move['amendment'],move['reason'],engine.now)
            accepts.clear()
            key=cycle_key(updated,engine.fixture['turn_order'].index(org))
            if key in seen_terms:
                cycle=(f"Version {updated['version']} has the same terms as version {seen_terms[key]} at the same point in the turn "
                       "order, so the counters are going round in a cycle; the disagreement is kept for each organization's staff, "
                       "and nothing commits automatically")
                break
            seen_terms[key]=updated['version']
        elif move['action']=='accept': accepts.add(org)
        elif move['action']=='request_hold':
            if move.get('resource_owner')!=org: raise ValueError('hold belongs to another owner')
            try:
                engine.protocol.hold(lot_id,d['version'],org,move['holds'],engine.now,engine.capacities(org,d))
            except Conflict as exc:
                # A hold that is already over (or double booked) is a refused move, not a crash.
                engine.records.event(lot_id,engine.now,'hold_refused',{'organization_id':org,'version':d['version'],'reason':str(exc)})
        with engine.records.transaction():
            # Read and write the lot in one transaction, so a concurrent change is never overwritten.
            lot=engine.records.get('lot',lot_id)
            queued=any(m['lot_id']==lot_id for m in engine.records.all('queued_move'))
            # A human's decline stays on the version: these exact terms never go back for approval.
            if lot['status']!='committed' and not queued and not declined_by(lot) and lot['draft']['allocations'] and all(lot['holds'].get(o) for o in named(lot['draft'])):
                lot['status']='awaiting_approvals'
                engine.records.put('lot',lot_id,lot)
                return lot
        if lot['status']=='committed': return lot
        if turn%len(engine.fixture['turn_order'])==0:
            no_change=no_change+1 if lot['draft']['version']==previous_version else 0
            if no_change>=engine.fixture['policies']['rounds_without_new_terms_before_disagreement']: break
    with engine.records.transaction():
        lot=engine.records.get('lot',lot_id)
        if lot['status']=='committed': return lot
        lot['status']='preserved_disagreement'
        declined=declined_by(lot)
        lot['stop_reason']=(cycle if cycle else
                            f"{', '.join(declined)} declined version {lot['draft']['version']} and the rounds that followed produced no new terms; no automatic commitment"
                            if declined else 'No approved feasible pathway after published negotiation rounds')
        engine.records.put('lot',lot_id,lot)
        engine.records.event(lot_id,engine.now,'preserved_disagreement',{'reason':lot['stop_reason']})
    return lot
