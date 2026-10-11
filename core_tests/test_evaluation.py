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

class EvaluationTests(unittest.TestCase):
    def test_baselines_and_replay_keep_checks_and_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            f=fixture(); r=evaluate(f,output=folder)
            self.assertEqual(len(r['methods']),4)
            self.assertFalse(r['methods'][3]['measured'])
            self.assertEqual(r['methods'][3]['status'],'not_run')
            for path in Path(folder).glob('*.json'):
                run=replay(path)
                self.assertTrue(all(run['rule_checks'].values()))
                self.assertEqual(run['mode'],'replay')


    def test_five_scenarios_report_whatever_happens(self):
        for path in Path('core_fixtures').glob('*.json'):
            f=json.loads(path.read_text())
            r=evaluate(f)
            self.assertEqual(r['scenario_id'],f['scenario_id'])
            self.assertTrue(all(m['invalid_commitments']==0 for m in r['methods'][:3]))


