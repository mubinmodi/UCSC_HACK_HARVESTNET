"""Schedule real owner moves for public offers, without scripted human decisions."""
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from .protocol import named

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


def negotiate_pending(engine,lot_id,provider=None):
    accepts=set()
    no_change=0
    previous_version=None
    for turn in range(1,201):
        lot=engine.records.get('lot',lot_id)
        d=lot['draft']
        if lot['status']=='committed': return lot
        org=engine.fixture['turn_order'][(turn-1)%len(engine.fixture['turn_order'])]
        if (turn-1)%len(engine.fixture['turn_order'])==0: previous_version=d['version']
        raw={'role':engine.roles[org],'draft':d,'facts':engine.facts(org,d),'turn':{'organization_id':org,'number':turn,'now':engine.now,'accepted_by':sorted(accepts)}}
        role,typed=parse_agent_input(raw)
        from harvestnet_agents.llm_negotiators import NumberPool,precompute
        pool=NumberPool();pool.add(typed);call_start=len(engine.calc.calls)
        pool.add(precompute(role,typed,engine.calc))
        def ask():
            return provider(org,{**raw,'turn':org,'turn_context':raw['turn'],'policy_session':engine.policy_session}) if provider else engine.rules_for(role,org).move(typed).to_dict()
        move=ask()
        for call in engine.calc.calls[call_start:]: pool.add(call.result)
        move=checked_move(engine,lot_id,org,move,pool,ask,lambda:engine.rules_for(role,org).move(typed).to_dict())
        try:
            queued=engine.records.get('queued_move',lot_id+':'+org)
        except KeyError:
            queued=None
        if queued:
            with engine.records.transaction(): engine.records.delete('queued_move',lot_id+':'+org)
            if queued['version']==d['version']: move={k:v for k,v in queued.items() if k!='lot_id'}
        if move['organization_id']!=org or move['version']!=d['version']:
            raise ValueError('owner move does not match published turn')
        if org=='advocate' and move['action'] not in ('counter','pass'):
            raise ValueError('advocate cannot vote')
        engine.records.event(lot_id,engine.now,'move',move)
        if move['action']=='counter':
            engine.protocol.amend(lot_id,d['version'],org,move['amendment'],move['reason'],engine.now)
            accepts.clear()
        elif move['action']=='accept': accepts.add(org)
        elif move['action']=='request_hold':
            if move.get('resource_owner')!=org: raise ValueError('hold belongs to another owner')
            engine.protocol.hold(lot_id,d['version'],org,move['holds'],engine.now,engine.capacities(org,d))
        lot=engine.records.get('lot',lot_id)
        queued=any(m['lot_id']==lot_id for m in engine.records.all('queued_move'))
        if not queued and lot['draft']['allocations'] and all(lot['holds'].get(o) for o in named(lot['draft'])):
            lot['status']='awaiting_approvals'
            with engine.records.transaction(): engine.records.put('lot',lot_id,lot)
            return lot
        if turn%len(engine.fixture['turn_order'])==0:
            no_change=no_change+1 if lot['draft']['version']==previous_version else 0
            if no_change>=engine.fixture['policies']['rounds_without_new_terms_before_disagreement']: break
    lot=engine.records.get('lot',lot_id)
    lot['status']='preserved_disagreement'
    lot['stop_reason']='No approved feasible pathway after published negotiation rounds'
    with engine.records.transaction():
        engine.records.put('lot',lot_id,lot)
        engine.records.event(lot_id,engine.now,'preserved_disagreement',{'reason':lot['stop_reason']})
    return lot
