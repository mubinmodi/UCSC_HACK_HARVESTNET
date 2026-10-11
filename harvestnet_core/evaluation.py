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


def coverage_by_food_bank(fixture, requests):
    """Design section 16: each food bank's average share of fair share received, over the
    households that chose it, zeros included. A household that chose several food banks
    counts in each of them. Food banks no household chose have no average."""
    out={}
    for bank in fixture['food_banks']:
        bid=bank['organization_id']
        cohort=[min(1,r.get('received_this_week_lb',0)/r['fair_share_lb']) for r in requests if bid in r.get('chosen_food_bank_ids',[])]
        if cohort:
            out[bid]=sum(cohort)/len(cohort)
    return out


def cooler_failure_report(run):
    """What Workflow 4 did with the run's faults, from the harness's own summaries."""
    faults=run.get('faults',[])
    return {"faults":len(faults),"handling":", ".join(sorted({f['handling'] for f in faults})),
            "changes_committed":sum(f.get('change_status')=='committed' for f in faults),
            "change_statuses":[f.get('change_status') for f in faults],
            "change_refusals":[r for f in faults for r in f.get('refusals',[])],
            "pounds_moved":sum(f.get('pounds_moved',0) for f in faults),
            "pickups_moved":sum(f.get('pickups_moved',0) for f in faults),
            "pickups_released":sum(f.get('pickups_released',0) for f in faults),
            "held_for_human_lb":sum(f.get('held_for_human_lb',0) for f in faults)}


def metrics(fixture, run, records):
    requests=records.all('request')
    collected=[p for p in records.all('pickup') if p['status']=='collected']
    total=sum(p['pounds'] for p in collected)
    offered=sum(i['pounds'] for lot in records.all('lot') for i in lot['draft']['items'])
    arrivals=[e for e in run['events'] if e['kind'] in ('commitment','change_commitment')]
    first=[e for e in arrivals if e['kind']=='commitment']
    start=min((dt(o['reported_at']) for o in fixture['surplus_offers']),default=dt(fixture['clock']['start']))
    checks=run['rule_checks']
    coverage=coverage_by_food_bank(fixture,requests)
    result={"produce_wasted_lb":max(0,offered-total),"worst_served_coverage":min(coverage.values()) if coverage else None,"coverage_by_food_bank":coverage,"households_reached":len({p['request_code'] for p in collected}),"pickup_window_match":sum(bool(p['window']) for p in collected)/len(collected) if collected else 0,"time_to_commitment_minutes":(min(dt(e['at']) for e in first)-start).total_seconds()/60 if first else None,"invalid_commitments":sum(not (checks.get('zero_invalid_commitments',False) and checks.get('no_double_booking',False)) for e in arrivals),"number_check_failures":sum(e['data'].get('count',0) for e in run['events'] if e['kind']=='number_check_failure')}
    if fixture.get('faults'):
        result['cooler_failure']=cooler_failure_report(run)
    return result


ACCOUNTING=('run_status','model_calls','llm_decisions','fallback_decisions','template_fallbacks')


def llm_accounting(run):
    """Label one run from its own provenance events, never from a cap shared with other runs."""
    provenance=[e['data'] for e in run['events'] if e['kind']=='policy_provenance']
    model_calls=sum(p.get('model_calls',0) for p in provenance)
    llm=sum(p.get('source')=='llm' for p in provenance)
    fallback=sum(p.get('source')!='llm' for p in provenance)
    templates=sum(e['kind']=='template_fallback' for e in run['events'])
    status='fallback_only' if model_calls==0 or llm==0 else 'partial' if fallback or templates else 'completed'
    return {"run_status":status,"model_calls":model_calls,"llm_decisions":llm,"fallback_decisions":fallback,"template_fallbacks":templates}


def llm_label(runs):
    totals={k:sum(r[k] for r in runs) for k in ACCOUNTING[1:]}
    statuses={r['run_status'] for r in runs}
    if statuses=={'fallback_only'}:
        return {**totals,"status":"fallback_only","measured":False,"reason":"No LLM decisions occurred in these runs; these are deterministic fallback outcomes"}
    if statuses=={'completed'}:
        return {**totals,"status":"completed","measured":True}
    return {**totals,"status":"partial","measured":True,"reason":f"{totals['fallback_decisions']} rules fallback and {totals['template_fallbacks']} template fallback decisions alongside {totals['llm_decisions']} LLM decisions; see each run"}


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
            if name=='llm' and hasattr(llm_provider,'pop_metadata'):
                metric.update(llm_accounting(run))
            runs.append(metric)
            if output:
                folder=Path(output); folder.mkdir(parents=True,exist_ok=True)
                (folder/f"{fixture['scenario_id']}-{name}-{repeat}.json").write_text(json.dumps({"fixture":fixture,"run":run,"metrics":metric},indent=2),encoding='utf-8')
            records.close()
        headline={k:v for k,v in runs[0].items() if k not in ACCOUNTING}
        methods.append({"method":name,"status":"completed","measured":True,**headline,"runs":runs,"variation":{k:{"mean":mean(r[k] for r in runs),"stddev":pstdev(r[k] for r in runs)} for k in ('produce_wasted_lb','worst_served_coverage','households_reached') if all(r[k] is not None for r in runs)}})
        if name=='llm' and hasattr(llm_provider,'pop_metadata'):
            methods[-1].update(llm_label(runs))
    note="Calculated from labeled scripted fixtures. produce_wasted_lb counts produce not collected by the scenario end; it is not observed spoilage. worst_served_coverage is the lowest food bank average of each chosen household's share of fair share received, zeros included. LLM not_run is not an LLM result."
    if fixture.get('faults'):
        note+=" The cooler failure is not known to any method before its time; Workflow 4 runs when it happens, and cooler_failure reports what it did."
    return {"scenario_id":fixture['scenario_id'],"run_mode":fixture['mode'],"synthetic":fixture['synthetic'],"measured":True,"note":note,"methods":methods,"headline":["produce_wasted_lb","worst_served_coverage"]}


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
