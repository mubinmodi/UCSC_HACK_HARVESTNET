import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from harvestnet_core.api import API
from harvestnet_core.calculators import Calculators
from harvestnet_core.engine import Engine,run_fixture
from harvestnet_core.protocol import Conflict,dt,terms_hash,named
from harvestnet_core.records import Records
from harvestnet_core.checks import rule_checks
from harvestnet_agents.calculators import HouseholdBalance,StandInCalculators
from harvestnet_agents.negotiation import StorageSlot,TimeWindow


from test_core import fixture

from harvestnet_core.evaluation import evaluate,replay

class LiveEvaluationTests(unittest.TestCase):
    def test_invalid_or_unauthorized_spending_caps_are_rejected(self):
        from harvestnet_core.live_evaluation import LLMProvider
        for cap in (float('nan'),float('inf'),True,-1,101):
            with self.assertRaises(ValueError): LLMProvider(None,limit_usd=cap)
        with self.assertRaises(ValueError): LLMProvider(None,limit_usd=1)

    def test_zero_cap_cannot_call_provider_or_claim_llm_measurement(self):
        from types import SimpleNamespace
        from harvestnet_core.live_evaluation import LLMProvider
        def forbidden(**kwargs): raise AssertionError('zero budget must not call a model')
        client=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=forbidden)))
        provider=LLMProvider(client,limit_usd=0)
        result=evaluate(fixture(),llm_provider=provider,repeats=2)
        self.assertEqual(provider.cap.spent_usd,0)
        self.assertEqual(result['methods'][-1]['status'],'fallback_only')
        self.assertFalse(result['methods'][-1]['measured'])
        with self.assertRaises(ValueError): LLMProvider(client,limit_usd=1)
        with self.assertRaises(ValueError): LLMProvider(client,limit_usd=101,allow_paid=True)


    def test_published_results_are_returned_unchanged(self):
        from harvestnet_core.live_evaluation import publish_evaluation
        f=fixture(); records=Records()
        result=publish_evaluation(f,records)
        api=API(Engine(f,records),clock=lambda:f['clock']['start'])
        status,response=api.call('GET','/results?scenario_id='+f['scenario_id'])
        self.assertEqual(status,200)
        self.assertEqual(response['methods'],result['methods'])


