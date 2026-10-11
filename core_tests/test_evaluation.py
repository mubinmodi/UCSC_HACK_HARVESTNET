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

from harvestnet_core.evaluation import evaluate,metrics,replay

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


SPLIT=('collected_by_households_lb','committed_to_food_banks_lb','produce_wasted_lb')


def one_lot(*, usable_until='2026-10-15T12:00:00-07:00', hold_end='2026-10-13T20:00:00-07:00', committed_lb=10, cooler=None, pickups=(('pk1','collected',4),)):
    """A 10 lb romaine lot committed to food bank ``a``: it arrives 3:20 pm, cold storage is held
    until ``hold_end``, and households collect 6-8 pm. All values synthetic."""
    records=Records()
    bank={'organization_id':'a','storage':[],'pickup_windows':[{'start':'2026-10-13T18:00:00-07:00','end':'2026-10-13T20:00:00-07:00'}]}
    if cooler: bank['cooler']=cooler
    lot={'draft':{'lot_id':'L','items':[{'produce_id':'romaine','pounds':10.0,'usable_until':usable_until}],
                  'transports':[{'food_bank_id':'a','mover':'food_bank','departs_at':'2026-10-13T15:00:00-07:00','arrives_at':'2026-10-13T15:20:00-07:00'}]},
         'status':'committed','commitments':[{'produce_id':'romaine','food_bank_id':'a','pounds':float(committed_lb)}] if committed_lb else [],
         'holds':{'a':[{'resource':'storage_cold','pounds':10.0,'start':'2026-10-13T15:20:00-07:00','end':hold_end}]}}
    with records.transaction():
        records.put('bank','a',bank)
        records.put('lot','L',lot)
        for pid,status,lb in pickups:
            records.put('pickup',pid,{'pickup_id':pid,'lot_id':'L','food_bank_id':'a','request_code':pid,'status':status,'pounds':float(lb),
                                      'items':[{'produce_id':'romaine','pounds':float(lb)}],'window':{}})
    f={'food_banks':[{'organization_id':'a'}],'surplus_offers':[],'clock':{'start':'2026-10-13T11:00:00-07:00'}}
    try:
        return metrics(f,{'events':[],'rule_checks':{}},records)
    finally:
        records.close()


def split(m):
    return tuple(m[k] for k in SPLIT)


class ProduceWastedTests(unittest.TestCase):
    """Design section 16, decided by the user October 11, 2026: produce committed to a food bank
    that can store it and hand it out before it stops being usable is not wasted."""

    def test_committed_and_storable_produce_is_not_wasted(self):
        m=one_lot()
        self.assertEqual(split(m),(4.0,6.0,0.0))
        self.assertEqual(m['uncollected_by_scenario_households_lb'],6.0)

    def test_produce_that_spoils_before_pickup_hours_is_wasted(self):
        self.assertEqual(split(one_lot(usable_until='2026-10-13T17:00:00-07:00')),(4.0,0.0,6.0))

    def test_storage_that_ends_before_pickup_hours_is_wasted(self):
        self.assertEqual(split(one_lot(hold_end='2026-10-13T17:30:00-07:00')),(4.0,0.0,6.0))

    def test_cold_produce_in_a_failed_cooler_is_wasted(self):
        cooler={'status':'failed','cold_available':False,'observed_at':'2026-10-13T23:00:00Z','synthetic':True}  # 4 pm local
        self.assertEqual(split(one_lot(cooler=cooler)),(4.0,0.0,6.0))

    def test_produce_with_no_commitment_is_wasted(self):
        self.assertEqual(split(one_lot(committed_lb=6)),(4.0,2.0,4.0))
        self.assertEqual(split(one_lot(committed_lb=0,pickups=())),(0.0,0.0,10.0))

    def test_collected_pounds_are_counted_once(self):
        # A pickup still waiting for its household is part of the food bank's committed pounds, not extra.
        m=one_lot(pickups=(('pk1','collected',4),('pk2','committed',3),('pk3','released',2)))
        self.assertEqual(split(m),(4.0,6.0,0.0))
        self.assertEqual(sum(split(m)),10.0)

    def test_every_scenario_and_method_reports_the_whole_split(self):
        for path in sorted(Path('core_fixtures').glob('*.json')):
            f=json.loads(path.read_text())
            for m in evaluate(f)['methods']:
                with self.subTest(scenario=f['scenario_id'],method=m['method']):
                    for k in SPLIT+('uncollected_by_scenario_households_lb',):
                        self.assertIn(k,m)
                    if m['status']=='not_run':
                        self.assertTrue(all(m[k] is None for k in SPLIT+('uncollected_by_scenario_households_lb',)))
                        continue
                    self.assertAlmostEqual(m['collected_by_households_lb']+m['uncollected_by_scenario_households_lb'],sum(split(m)))
                    self.assertLessEqual(m['produce_wasted_lb'],m['uncollected_by_scenario_households_lb']+1e-9)
                    self.assertTrue(all(v>=0 for v in split(m)))

    def test_normal_afternoon_no_longer_counts_food_bank_produce_as_wasted(self):
        f=json.loads(Path('core_fixtures/normal-afternoon.json').read_text())
        for m in evaluate(f)['methods'][:3]:
            with self.subTest(method=m['method']):
                self.assertGreater(m['committed_to_food_banks_lb'],0)
                self.assertLess(m['produce_wasted_lb'],m['uncollected_by_scenario_households_lb'])

    def test_cooler_failure_waste_shows_until_workflow_4_commits(self):
        shipped=json.loads(Path('core_fixtures/cooler-failure.json').read_text())
        prompt=copy.deepcopy(shipped)
        for h in prompt['humans']:
            h['after_minutes']=min(h['after_minutes'],5)
        for a,b in zip(evaluate(shipped)['methods'][:3],evaluate(prompt)['methods'][:3]):
            with self.subTest(method=a['method']):
                # The shipped fixture's refused late answer leaves cold produce in a failed cooler.
                self.assertGreaterEqual(a['produce_wasted_lb'],a['cooler_failure']['held_for_human_lb'])
                self.assertGreater(a['produce_wasted_lb'],0)
                self.assertLess(b['produce_wasted_lb'],a['produce_wasted_lb'])


