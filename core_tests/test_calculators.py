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

class CalculatorTests(unittest.TestCase):
    def test_signed_adjustments_are_finite_and_never_negative(self):
        calc=Calculators()
        self.assertEqual(calc.adjust_pounds(5,3),8)
        self.assertEqual(calc.adjust_pounds(5,-2),3)
        self.assertEqual(calc.adjust_pounds(5,-10),0)
        for invalid in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError): calc.adjust_pounds(5,invalid)
        with self.assertRaises(ValueError): calc.adjust_pounds(-1,2)
        with self.assertRaises(ValueError): calc.adjust_pounds(1e308,1e308)

    def test_new_teammate_surplus_bid_uses_real_calculator(self):
        from harvestnet_agents.negotiation import parse_agent_input
        raw=json.loads(Path('agents/tests/fixtures/negotiators/eastside_bids_beyond_fair_share_once_its_households_have_it.json').read_text())
        role,typed=parse_agent_input(raw)
        e=Engine(json.loads(Path('docs/contracts/examples/scenario-normal-afternoon.json').read_text()))
        move=e.rules_for(role,typed.turn.organization_id).move(typed).to_dict()
        self.assertEqual(move['amendment']['pounds'],200)
        self.assertIn('beyond fair share',move['reason'])
        self.assertIn('adjust_pounds',[call.name for call in e.calc.calls])

    def test_merged_teammate_runner_uses_real_calculators(self):
        from harvestnet_agents.scenario import load_scenario
        from harvestnet_agents.scenario_runner import FIXTURE_CHECKS_IN_HARNESS, run_scenario
        calc=Calculators()
        result=run_scenario(load_scenario(fixture()),calculators=calc)
        self.assertEqual(result.status,'committed')
        self.assertTrue(calc.calls)
        self.assertTrue(all(result.rule_checks().values()))
        # Lane B's runner leaves the fixture's checks to the harness; the join (#20) runs them.
        self.assertTrue(all(value==FIXTURE_CHECKS_IN_HARNESS for value in result.fixture_rule_checks.values()))
        self.assertTrue(all(not e.get('difference_from_stand_in') for e in result.events if e['kind']=='calculator_call'))


    def test_water_fill_contract_example_and_excess(self):
        c=Calculators()
        h=[{'request_code':'a','household_size':4,'received_lb':0},{'request_code':'b','household_size':1,'received_lb':0},{'request_code':'c','household_size':1,'received_lb':4}]
        result=c.household_portions(10,h)
        self.assertEqual([p['pounds'] for p in result['portions']],[9,1,0])
        result=c.household_portions(30,h)
        self.assertEqual(result['left_over_lb'],14)
        self.assertTrue(all(p['still_below_lb']==0 for p in result['portions']))
        self.assertNotIsInstance(c,StandInCalculators)


    def test_calculators_do_not_guess_or_accept_nan(self):
        c=Calculators()
        for invalid in (float('nan'),float('inf'),-1,True):
            with self.assertRaises(ValueError): c.household_portions(invalid,[])
        for invalid in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError): c.capacity_fit(invalid,1)
        self.assertFalse(c.capacity_fit(-1,1).fits)
        with self.assertRaises(ValueError): c.to_pounds('apples',1,'case')
        self.assertEqual(c.to_pounds('potatoes',8,'sack',50),400)
        self.assertEqual(c.fair_share(6).pounds,16)
        self.assertEqual(c.fair_share_gap([HouseholdBalance(2,3)]).gap_lb,4)


    def test_storage_boundaries_and_missing_reading(self):
        c=Calculators(); start=dt('2026-10-13T12:00:00-07:00'); end=start+timedelta(hours=1)
        s=StorageSlot(TimeWindow(start,end),10,20)
        self.assertTrue(c.storage_at([s],start).recorded)
        self.assertFalse(c.storage_at([s],end).recorded)
        self.assertEqual(c.storage_at([s,StorageSlot(TimeWindow(start,end),5,15)],start).cold_free_lb,5)


    def test_pickup_and_limited_fridge(self):
        e=Engine(fixture()); r=e.records.get('request','TEST1'); bank=e.records.get('bank','city')
        item={'produce_id':'romaine','usable_until':'2026-10-15T12:00:00-07:00'}
        r['limited_fridge']=True
        self.assertIsNotNone(e.eligible(r,bank,item,dt('2026-10-13T14:00:00-07:00')))
        bank['pickup_windows']=bank['pickup_windows'][1:]
        self.assertIsNone(e.eligible(r,bank,item,dt('2026-10-13T14:00:00-07:00')))
        item['produce_id']='apples'
        self.assertIsNotNone(e.eligible(r,bank,item,dt('2026-10-13T14:00:00-07:00')))


class MatchingProtocolTests(unittest.TestCase):
    def test_two_number_failures_then_template_fallback(self):
        from harvestnet_core.stand_ins import StandInAgents
        stand=StandInAgents()
        def bad(org,wire):
            return {**stand(org,wire),'reason':'Owner claims 999999 lb'}
        r=run_fixture(fixture(),bad)
        self.assertTrue(all(r['rule_checks'].values()))
        failures=[e for e in r['events'] if e['kind']=='number_check_failure']
        self.assertGreaterEqual(len(failures),2)
        self.assertIn('template_fallback',[e['kind'] for e in r['events']])


    def test_recall_never_offered(self):
        f=fixture(); f['surplus_offers'][0]['recall_notice']=True
        records=Records(); r=run_fixture(f,records=records)
        self.assertEqual(records.all('lot'),[])
        self.assertEqual(r['commitments'],[])


    def test_new_version_invalidates_old_approvals_receipts(self):
        f=fixture(); f['humans']=[]; records=Records(); run_fixture(f,records=records)
        e=Engine(f,records); lot=records.all('lot')[0]; d=lot['draft']
        receipt={'lot_id':d['lot_id'],'version':d['version'],'organization_id':'market','terms_hash':terms_hash(d),'decision':'approve','receipt_id':'r1'}
        first=e.protocol.approve(receipt,'market',e.now,e.validate)
        self.assertEqual(e.protocol.approve(receipt,'market',e.now,e.validate),first)
        with self.assertRaises(Conflict): e.protocol.approve({**receipt,'decision':'decline'},'market',e.now,e.validate)
        updated=e.protocol.amend(d['lot_id'],d['version'],'city',{'kind':'set_pounds','produce_id':'apples','food_bank_id':'city','pounds':3},'Smaller owner allocation',e.now)
        self.assertEqual(updated['version'],d['version']+1)
        self.assertEqual(records.get('lot',d['lot_id'])['approvals'],{})
        with self.assertRaises(Conflict): e.protocol.approve({**receipt,'receipt_id':'new'},'market',e.now,e.validate)


