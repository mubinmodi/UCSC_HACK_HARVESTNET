"""Lane A's replaceable stand-in agents, explicitly separate from real Lane B rules."""
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.profiles import STORAGE_COLD, STORAGE_DRY
from .calculators import Calculators
from .engine import jsonable


class StandInAgents:
    label='Lane A deterministic stand-in agents'
    def __init__(self): self.calc=Calculators()

    def __call__(self,org,wire):
        role,input=parse_agent_input({**wire,'turn':wire['turn_context']})
        d=input.draft; facts=input.facts
        base={'organization_id':org,'version':d.version,'reason':'Labeled stand-in owner move; human approval is still required'}
        voters={d.donor_id}|{a.food_bank_id for a in d.allocations if a.pounds>0}
        all_accepted=voters<=set(input.turn.accepted_by)
        if role.value=='advocate': return {**base,'action':'pass'}
        if role.value=='donor':
            if not d.allocations: return {**base,'action':'pass'}
            if all_accepted:
                holds=[{'resource':'lot','pounds':sum(a.pounds for a in d.allocations),'start':input.turn.now.isoformat(),'end':d.deadline.isoformat()}]
                drop=[t for t in d.transports if t.mover.value=='donor']
                if drop:
                    holds.append({'resource':'drop_off','pounds':sum(a.pounds for a in d.allocations if any(t.food_bank_id==a.food_bank_id for t in drop)),'start':min(t.departs_at for t in drop).isoformat(),'end':max(t.arrives_at for t in drop).isoformat()})
                return {**base,'action':'request_hold','resource_owner':org,'holds':holds}
            return {**base,'action':'accept'}
        own=d.allocations_to(org)
        transport=d.transport(org)
        if own and not transport:
            if not facts.truck: return {**base,'action':'reject'}
            depart=facts.truck.window.start
            return {**base,'action':'counter','amendment':{'kind':'set_transport','food_bank_id':org,'mover':'food_bank','departs_at':depart.isoformat(),'arrives_at':self.calc.arrival_time(depart,facts.travel_minutes_from_donor).isoformat()}}
        if own:
            if all_accepted:
                end=max(w.end for w in facts.pickup_windows)
                holds=[]
                for resource in (STORAGE_COLD,STORAGE_DRY):
                    pounds=sum(a.pounds for a in own if self.calc.profiles.get(a.produce_id).storage_resource==resource)
                    if pounds: holds.append({'resource':resource,'pounds':pounds,'start':transport.arrives_at.isoformat(),'end':end.isoformat()})
                if transport.mover.value=='food_bank': holds.append({'resource':'truck','pounds':sum(a.pounds for a in own),'start':transport.departs_at.isoformat(),'end':transport.arrives_at.isoformat()})
                return {**base,'action':'request_hold','resource_owner':org,'holds':holds}
            return {**base,'action':'accept'}
        if not facts.truck or facts.travel_minutes_from_donor is None: return {**base,'action':'pass'}
        arrival=self.calc.arrival_time(facts.truck.window.start,facts.travel_minutes_from_donor)
        space=self.calc.storage_at(facts.storage,arrival)
        for item in d.items:
            cold=self.calc.profiles.get(item.produce_id).storage_resource==STORAGE_COLD
            available=d.unallocated_lb(item.produce_id)
            pounds=min(available,facts.demand.below_fair_share_lb,facts.truck.capacity_lb,space.cold_free_lb if cold else space.dry_free_lb)
            if pounds>0 and (not cold or facts.truck.refrigerated) and self.calc.pickup_feasibility(arrival,facts.pickup_windows,item.usable_until).feasible:
                return {**base,'action':'counter','amendment':{'kind':'set_pounds','food_bank_id':org,'produce_id':item.produce_id,'pounds':pounds}}
        return {**base,'action':'pass'}
