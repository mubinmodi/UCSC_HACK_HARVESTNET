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


def fixture():
    f=json.loads(Path('docs/contracts/examples/scenario-normal-afternoon.json').read_text())
    f['faults']=[]
    f['food_banks']=f['food_banks'][:1]
    f['organizations']=[o for o in f['organizations'] if o['organization_id'] in ('market','city','advocate')]
    f['turn_order']=['market','city','advocate']
    f['requests']=[{**f['requests'][0],'request_code':'TEST1','household_size':1,'chosen_food_bank_ids':['city'],'limited_fridge':False,'cant_eat':[],'language':'en'}]
    f['donors'][0]['drop_off']['food_bank_ids']=['city']
    f['surplus_offers'][0]['items']=f['surplus_offers'][0]['items'][:1]
    f['surplus_offers'][0]['items'][0]['quantity']=4
    f['household_replies']=[{'request_code':'TEST1','on_pickup_notice':'collect'}]
    return f


class HarnessTests(unittest.TestCase):
    def test_replaceable_lane_a_stand_ins(self):
        from stand_ins import StandInAgents
        r=run_fixture(fixture(),StandInAgents())
        self.assertTrue(r['commitments'])
        self.assertIn('stand-in',r['policy_label'])
        self.assertTrue(all(r['rule_checks'].values()))


    def test_real_normal_run_commits_confirms_and_audits(self):
        records=Records(); r=run_fixture(fixture(),records=records)
        self.assertTrue(r['commitments'])
        self.assertTrue(all(r['rule_checks'].values()))
        self.assertIn('pickup_confirmation',[e['kind'] for e in r['events']])
        self.assertEqual(records.get('request','TEST1')['received_this_week_lb'],4)


    def test_no_human_answer_and_decline_never_commit(self):
        for humans in ([],[{'organization_id':'market','on_approval_request':'decline','after_minutes':1}]):
            f=fixture(); f['humans']=humans
            r=run_fixture(f)
            self.assertEqual(r['commitments'],[])
            self.assertTrue(all(r['rule_checks'].values()))
            self.assertTrue(all(p['status']=='unclaimed' for p in r['pathways']))


    def test_expired_hold_prevents_commitment(self):
        records=Records(); f=fixture(); f['humans']=[]
        run_fixture(f,records=records)
        lot=records.all('lot')[0]; d=lot['draft']; e=Engine(f,records)
        for owner in named(d):
            e.protocol.approve({'lot_id':d['lot_id'],'version':d['version'],'organization_id':owner,'terms_hash':terms_hash(d),'decision':'approve'},owner,'2026-10-13T14:59:00-07:00',e.validate)
        self.assertNotEqual(records.get('lot',d['lot_id'])['status'],'committed')


    def test_audit_detects_tampered_approval_and_double_booking(self):
        records=Records(); run=run_fixture(fixture(),records=records)
        lot=records.all('lot')[0]; lid=lot['draft']['lot_id']
        event=next(e for e in records.events(lid) if e['kind']=='commitment')
        event['data']['approvals']['market']['version']=999
        records.execute('UPDATE events SET data=? WHERE sequence=?',(json.dumps(event['data']),event['sequence']))
        checks=rule_checks(records,lid,run['pathways'],{('market','lot'):4,('market','drop_off'):700,('city','storage_dry'):200,('city','truck'):250})
        self.assertFalse(checks['versioned_approvals'])
        self.assertFalse(checks['no_auto_commit'])
        second=copy.deepcopy(lot); second['draft']['lot_id']='other'; records.put('lot','other',second)
        checks=rule_checks(records,lid,run['pathways'],{('market','lot'):4,('market','drop_off'):700,('city','storage_dry'):4,('city','truck'):250})
        self.assertFalse(checks['no_double_booking'])


    def test_store_rollback_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'core.sqlite'); records=Records(path)
            with self.assertRaises(ValueError):
                with records.transaction():
                    records.put('x','1',{'a':1}); raise ValueError()
            self.assertEqual(records.all('x'),[])
            run=run_fixture(fixture(),records=records); before=records.get('request','TEST1')
            records.close(); records=Records(path); Engine(fixture(),records)
            self.assertEqual(records.get('request','TEST1'),before)
            self.assertTrue(records.events(fixture()['surplus_offers'][0]['lot_id']))
            records.close()


