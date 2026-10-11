"""Same fixture and safety rules for every method; replay never calls a model."""
import copy
import json
from pathlib import Path
from statistics import mean, pstdev
from harvestnet_agents.negotiation import parse_agent_input, Move, MoveKind
from harvestnet_agents.rules_negotiators import rules_negotiator
from .engine import Engine, run_fixture
from .protocol import dt
from .records import Records


class Baseline:
    """Food banks bid in baseline priority order, subject to their own real review.

The priority controls who gets a first opportunity; it does not approve for them.
"""
    def __init__(self, fixture, method):
        self.fixture=fixture
        self.method=method
        self.engine=Engine(fixture)
        rs=fixture['requests']
        banks=[b['organization_id'] for b in fixture['food_banks']]
        if method=='first_come_first_served':
            self.priority=sorted(banks,key=lambda b:min((dt(r['submitted_at']) for r in rs if b in r['chosen_food_bank_ids']),default=dt(fixture['clock']['end'])))
        elif method=='nearest_food_bank':
            donor=fixture['donors'][0]
            self.priority=sorted(banks,key=lambda b:(donor['travel_minutes'].get(b,float('inf')),b))
        else:
            raise ValueError('unknown baseline')
        self.passed=set()

    def __call__(self, org, wire):
        role,typed=parse_agent_input({**wire,'turn':wire['turn_context']})
        if org=='advocate':
            return Move(org,role,typed.draft.version,MoveKind.PASS,'Baseline has no advocate amendments').to_dict()
        if role.value=='food_bank':
            # Allow earlier banks to finish requesting before the next bank bids.
            outstanding=[b for b in self.priority if b not in self.passed]
            if outstanding and outstanding[0]!=org and not typed.draft.allocations_to(org):
                return Move(org,role,typed.draft.version,MoveKind.PASS,'Waiting for baseline priority turn').to_dict()
        move=self.engine.rules_for(role,org).move(typed)
        if role.value=='food_bank' and move.kind in (MoveKind.ACCEPT,MoveKind.PASS,MoveKind.REJECT):
            self.passed.add(org)
        return move.to_dict()


def metrics(fixture, run, records):
    requests=records.all('request')
    collected=[p for p in records.all('pickup') if p['status']=='collected']
    total=sum(p['pounds'] for p in collected)
    offered=sum(i['pounds'] for lot in records.all('lot') for i in lot['draft']['items'])
    arrivals=[e for e in run['events'] if e['kind']=='commitment']
    start=min((dt(o['reported_at']) for o in fixture['surplus_offers']),default=dt(fixture['clock']['start']))
    checks=run['rule_checks']
    return {"produce_wasted_lb":max(0,offered-total),"worst_served_coverage":min((min(1,r.get('received_this_week_lb',0)/r['fair_share_lb']) for r in requests),default=0),"households_reached":len({p['request_code'] for p in collected}),"pickup_window_match":sum(bool(p['window']) for p in collected)/len(collected) if collected else 0,"time_to_commitment_minutes":(min(dt(e['at']) for e in arrivals)-start).total_seconds()/60 if arrivals else None,"invalid_commitments":sum(not (checks.get('zero_invalid_commitments',False) and checks.get('no_double_booking',False)) for e in arrivals),"number_check_failures":sum(e['data'].get('count',0) for e in run['events'] if e['kind']=='number_check_failure')}


def evaluate(fixture, *, llm_provider=None, repeats=1, output=None):
    if isinstance(repeats,bool) or repeats<1:
        raise ValueError('positive repeat count required')
    methods=[]
    for name in ('first_come_first_served','nearest_food_bank','rules_based','llm'):
        if name=='llm' and llm_provider is None:
            methods.append({"method":name,"status":"not_run","reason":"No authorized capped LLM provider configured","measured":False,"produce_wasted_lb":None,"worst_served_coverage":None,"households_reached":None,"invalid_commitments":None})
            continue
        runs=[]
        for repeat in range(repeats if name=='llm' else 1):
            provider=llm_provider if name=='llm' else Baseline(fixture,name) if name!='rules_based' else None
            records=Records()
            run=run_fixture(copy.deepcopy(fixture),provider,records=records)
            metric=metrics(fixture,run,records)
            runs.append(metric)
            if output:
                folder=Path(output); folder.mkdir(parents=True,exist_ok=True)
                (folder/f"{fixture['scenario_id']}-{name}-{repeat}.json").write_text(json.dumps({"fixture":fixture,"run":run,"metrics":metric},indent=2),encoding='utf-8')
            records.close()
        methods.append({"method":name,"status":"completed","measured":True,**runs[0],"runs":runs,"variation":{k:{"mean":mean(r[k] for r in runs),"stddev":pstdev(r[k] for r in runs)} for k in ('produce_wasted_lb','worst_served_coverage','households_reached')}})
        if name=='llm' and hasattr(llm_provider,'cap') and not llm_provider.cap.entries:
            methods[-1].update(status='fallback_only',measured=False,reason='No LLM calls occurred; these are deterministic fallback outcomes')
    return {"scenario_id":fixture['scenario_id'],"run_mode":fixture['mode'],"measured":True,"note":"Calculated from labeled scripted fixtures. produce_wasted_lb counts produce not collected by the scenario end; it is not observed spoilage. LLM not_run is not an LLM result.","methods":methods,"headline":["produce_wasted_lb","worst_served_coverage"]}


def replay(path):
    saved=json.loads(Path(path).read_text(encoding='utf-8'))
    moves=[e['data'] for e in saved['run']['events'] if e['kind']=='move']
    index=0
    def provider(org,wire):
        nonlocal index
        if index>=len(moves): raise ValueError('replay moves exhausted')
        move=moves[index]; index+=1
        if move['organization_id']!=org or move['version']!=wire['draft']['version']:
            raise ValueError('replay diverged from recorded turn')
        return copy.deepcopy(move)
    fixture={**saved['fixture'],'mode':'replay'}
    run=run_fixture(fixture,provider)
    if index!=len(moves) or run['commitments']!=saved['run']['commitments'] or run['pathways']!=saved['run']['pathways'] or run['rule_checks']!=saved['run']['rule_checks']:
        raise ValueError('replay outcomes diverged')
    return run
