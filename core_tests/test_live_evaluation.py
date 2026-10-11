from types import SimpleNamespace
import unittest
from harvestnet_core.api import API
from harvestnet_core.engine import Engine,run_fixture
from harvestnet_core.records import Records
from harvestnet_core.stand_ins import StandInAgents
from harvestnet_agents.llm_negotiators import CostEntry,SpendingCap

from test_core import fixture

from harvestnet_core.evaluation import evaluate


def forbidden_client():
    def forbidden(**kwargs): raise AssertionError('this budget must not call a model')
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=forbidden)))


def spend(cap,usd):
    cap.entries.append(CostEntry('earlier','food_bank','claude-opus-5-5',0,0,0,0,usd,usd))


class ScriptedProvider:
    """Stand-in moves with scripted LLM provenance; no model is called."""
    label='scripted provenance (test only)'
    def __init__(self,provenance,*,cap=None,cost_per_llm_call=0.0):
        self.inner=StandInAgents(); self.provenance=provenance; self.calls=0
        self.cap=cap or SpendingCap(1.0); self.cost=cost_per_llm_call; self.metadata=None; self.issued=[]
    def __call__(self,org,wire):
        self.calls+=1
        source=self.provenance(self.calls)
        calls=1 if source=='llm' else 0
        if calls and self.cost: spend(self.cap,self.cost)
        self.metadata={'source':source,'model_calls':calls,'number_check_failures':0,'cost_usd':self.cost*calls,'fallback_reason':None if calls else 'spending cap'}
        self.issued.append(self.metadata)
        return self.inner(org,wire)
    def pop_metadata(self):
        metadata=self.metadata; self.metadata=None
        return metadata


class LiveEvaluationTests(unittest.TestCase):
    def test_invalid_or_unauthorized_spending_caps_are_rejected(self):
        from harvestnet_core.live_evaluation import LLMProvider
        for cap in (float('nan'),float('inf'),True,-1,101):
            with self.assertRaises(ValueError): LLMProvider(None,limit_usd=cap)
        with self.assertRaises(ValueError): LLMProvider(None,limit_usd=1)

    def test_zero_cap_cannot_call_provider_or_claim_llm_measurement(self):
        from harvestnet_core.live_evaluation import LLMProvider
        client=forbidden_client()
        provider=LLMProvider(client,limit_usd=0)
        result=evaluate(fixture(),llm_provider=provider,repeats=2)
        self.assertEqual(provider.cap.spent_usd,0)
        self.assertEqual(result['methods'][-1]['status'],'fallback_only')
        self.assertFalse(result['methods'][-1]['measured'])
        with self.assertRaises(ValueError): LLMProvider(client,limit_usd=1)
        with self.assertRaises(ValueError): LLMProvider(client,limit_usd=101,allow_paid=True)

    def test_zero_cap_without_a_client_needs_no_sdk(self):
        from unittest import mock
        from harvestnet_core.live_evaluation import LLMProvider
        provider=LLMProvider(None,limit_usd=0)
        def no_sdk(): raise AssertionError('a zero cap must not build the Anthropic client')
        with mock.patch('harvestnet_agents.llm_negotiators._default_client',no_sdk):
            result=evaluate(fixture(),llm_provider=provider)
        self.assertEqual(result['methods'][-1]['status'],'fallback_only')
        self.assertEqual(provider.cap.spent_usd,0)

    def test_all_fallback_run_after_earlier_spend_is_fallback_only(self):
        from harvestnet_core.live_evaluation import LLMProvider
        provider=LLMProvider(forbidden_client(),limit_usd=1,allow_paid=True)
        spend(provider.cap,1.0)  # an earlier scenario used the whole shared cap
        llm=evaluate(fixture(),llm_provider=provider)['methods'][-1]
        self.assertEqual(llm['status'],'fallback_only')
        self.assertFalse(llm['measured'])
        self.assertEqual(llm['runs'][0]['llm_decisions'],0)
        self.assertGreater(llm['runs'][0]['fallback_decisions'],0)
        self.assertEqual(llm['runs'][0]['model_calls'],0)

    def test_run_that_hits_the_cap_midway_is_visibly_partial(self):
        provider=ScriptedProvider(lambda n:'llm' if n<=2 else 'fallback')
        llm=evaluate(fixture(),llm_provider=provider)['methods'][-1]
        self.assertEqual(llm['status'],'partial')
        self.assertTrue(llm['measured'])
        self.assertIn('fallback',llm['reason'])
        run=llm['runs'][0]
        self.assertEqual((run['llm_decisions'],run['model_calls']),(2,2))
        self.assertEqual(run['fallback_decisions'],provider.calls-2)
        self.assertEqual(run['run_status'],'partial')

    def test_fully_llm_run_is_completed(self):
        llm=evaluate(fixture(),llm_provider=ScriptedProvider(lambda n:'llm'))['methods'][-1]
        self.assertEqual(llm['status'],'completed')
        self.assertEqual(llm['runs'][0]['fallback_decisions'],0)

    def test_published_cost_is_this_scenarios_spend_not_the_cap_total(self):
        from harvestnet_core.live_evaluation import publish_evaluation
        provider=ScriptedProvider(lambda n:'llm',cost_per_llm_call=0.01)
        spend(provider.cap,0.25)  # an earlier scenario on the same shared cap
        result=publish_evaluation(fixture(),Records(),llm_provider=provider)
        self.assertAlmostEqual(result['llm_cost_usd'],0.01*provider.calls)
        self.assertAlmostEqual(result['llm_cap_spent_usd'],0.25+0.01*provider.calls)
        self.assertEqual(result['llm_cap_usd'],1.0)

    def test_retry_after_number_check_failure_records_both_calls(self):
        provider=ScriptedProvider(lambda n:'llm',cost_per_llm_call=0.01)
        inner=provider.inner
        class BadFirst:
            def __init__(self): self.first=True
            def __call__(self,org,wire):
                move=inner(org,wire)
                if self.first: self.first=False; move={**move,'reason':'Owner claims 999999 lb'}
                return move
        provider.inner=BadFirst()
        run=run_fixture(fixture(),provider)
        self.assertIn('number_check_failure',[e['kind'] for e in run['events']])
        provenance=[e['data'] for e in run['events'] if e['kind']=='policy_provenance']
        self.assertEqual(len(provenance),len(provider.issued))
        self.assertEqual(sum(p['model_calls'] for p in provenance),provider.calls)
        self.assertAlmostEqual(sum(p['cost_usd'] for p in provenance),sum(m['cost_usd'] for m in provider.issued))

    def test_published_results_are_returned_unchanged(self):
        from harvestnet_core.live_evaluation import publish_evaluation
        f=fixture(); records=Records()
        result=publish_evaluation(f,records)
        api=API(Engine(f,records),clock=lambda:f['clock']['start'])
        status,response=api.call('GET','/results?scenario_id='+f['scenario_id'])
        self.assertEqual(status,200)
        self.assertEqual(response['methods'],result['methods'])
