import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from harvestnet_core.api import API
from harvestnet_core.calculators import Calculators
from harvestnet_core.engine import Engine,run_fixture
from harvestnet_core.evaluation import evaluate,replay
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


class CalculatorTests(unittest.TestCase):
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
            with self.assertRaises(ValueError): c.capacity_fit(invalid,1)
            with self.assertRaises(ValueError): c.household_portions(invalid,[])
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


class HarnessTests(unittest.TestCase):
    def test_replaceable_lane_a_stand_ins(self):
        from harvestnet_core.stand_ins import StandInAgents
        r=run_fixture(fixture(),StandInAgents())
        self.assertTrue(r['commitments'])
        self.assertIn('stand-in',r['policy_label'])
        self.assertTrue(all(r['rule_checks'].values()))

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

    def test_recall_never_offered(self):
        f=fixture(); f['surplus_offers'][0]['recall_notice']=True
        records=Records(); r=run_fixture(f,records=records)
        self.assertEqual(records.all('lot'),[])
        self.assertEqual(r['commitments'],[])

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


class APITests(unittest.TestCase):
    def setUp(self):
        self.f=fixture(); self.e=Engine(self.f)
        self.now='2026-10-13T12:00:00-07:00'
        self.api=API(self.e,clock=lambda:self.now,staff_tokens={'market':'donor-test','city':'city-test'})
        self.form={k:self.f['requests'][0][k] for k in ('household_size','pickup_windows','limited_fridge','neighborhood','cant_eat','snap','language')}

    def test_consent_privacy_and_seven_day_deletion(self):
        status,preview=self.api.call('POST','/requests/preview',self.form)
        self.assertEqual(status,200); self.assertFalse(preview['saved'])
        self.assertEqual(self.api.call('POST','/requests',self.form)[0],400)
        status,r=self.api.call('POST','/requests',{**self.form,'consent':True,'phone':'+15555550142'})
        self.assertEqual(status,201); self.assertEqual(r['fair_share_lb'],4)
        self.assertNotIn('phone',r)
        self.assertTrue(self.e.records.get('phone',r['request_code']))
        self.now='2026-10-20T12:00:00-07:00'
        self.assertEqual(self.api.call('GET','/requests/'+r['request_code'])[0],404)
        self.assertEqual(self.e.records.all('phone'),[])
        self.assertEqual(self.api.call('POST','/requests',{**self.form,'consent':True,'name':'private'})[0],400)

    def test_owner_authentication_and_no_pending_pickup_leak(self):
        self.assertEqual(self.api.call('GET','/food-banks/city/dashboard')[0],401)
        self.assertEqual(self.api.call('GET','/food-banks/city/dashboard',token='donor-test')[0],401)
        self.assertEqual(self.api.call('GET','/food-banks/city/dashboard',token='city-test')[0],200)
        self.assertEqual(self.api.call('GET','/requests/TEST1')[1]['pickups'],[])

    def test_deadline_records_unclaimed_never_commits(self):
        offer=copy.deepcopy(self.f['surplus_offers'][0])
        status,created=self.api.call('POST','/surplus-offers',offer,token='donor-test')
        self.assertEqual(status,201)
        self.now='2026-10-13T15:00:00-07:00'
        status,lot=self.api.call('GET','/lots/'+created['lot_id'])
        self.assertEqual(status,200)
        self.assertEqual(lot['status'],'unclaimed')
        self.assertEqual(self.e.records.get('lot',created['lot_id'])['commitments'],[])

    def test_voice_replay_creates_same_share_only_after_consent(self):
        data=json.loads(Path('agents/tests/fixtures/front_desk/en_complete.json').read_text())
        api=API(self.e,clock=lambda:self.now,extractor=lambda transcript:data['extractor_output'])
        status,r=api.call('POST','/voice-intake',{'transcript':data['transcript'],'call_id':'recorded'})
        self.assertEqual(status,200); self.assertTrue(r['complete']); self.assertFalse(r['saved'])
        self.assertEqual(r['fair_share_lb'],12)
        status,saved=api.call('POST','/requests',{**r['draft_request'],'consent':True,'channel':'voice'})
        self.assertEqual(status,201); self.assertEqual(saved['fair_share_lb'],12)
        self.assertEqual(self.api.call('POST','/voice-intake',{})[0],503)

    def test_release_wrong_code_rejected_and_retry_safe(self):
        f=fixture(); f['household_replies']=[]; records=Records(); run_fixture(f,records=records)
        e=Engine(f,records); api=API(e,clock=lambda:'2026-10-13T18:00:00-07:00')
        p=records.all('pickup')[0]
        self.assertEqual(api.call('POST','/pickups/'+p['pickup_id']+'/release',{'request_code':'wrong'})[0],401)
        self.assertTrue(api.call('POST','/pickups/'+p['pickup_id']+'/release',{'request_code':'TEST1'})[1]['released'])
        self.assertTrue(api.call('POST','/pickups/'+p['pickup_id']+'/release',{'request_code':'TEST1'})[1]['released'])

    def test_contract_operations_are_real_and_top_level_shapes_match(self):
        for operation,target,body in [('get_health','/health',None),('get_fair_share','/fair-share?household_size=4',None),('list_produce_profiles','/produce-profiles',None),('list_food_banks','/food-banks',None),('preview_request','/requests/preview',self.form),('get_request','/requests/TEST1',None),('get_food_bank_dashboard','/food-banks/city/dashboard',None),('list_approvals','/approvals?organization_id=city',None)]:
            example=json.loads(Path('docs/contracts/examples/public-api/'+operation+'.json').read_text())
            status,result=self.api.call(example['method'],target,body,token='city-test')
            self.assertEqual(status,200,(operation,result))
            self.assertTrue(set(example['example']['response']['body'])<=set(result),(operation,result))
            self.assertNotEqual(result['mode'],'example')

    def test_offer_to_own_human_approvals_and_public_pickup(self):
        offer=copy.deepcopy(self.f['surplus_offers'][0])
        status,created=self.api.call('POST','/surplus-offers',offer,token='donor-test')
        self.assertEqual(status,201,created)
        lid=created['lot_id']
        lot=self.e.records.get('lot',lid)
        self.assertEqual(lot['status'],'awaiting_approvals')
        self.assertEqual(lot['approvals'],{})
        self.assertEqual(self.api.call('GET','/requests/TEST1')[1]['pickups'],[])
        d=lot['draft']
        for owner,token in [('market','donor-test'),('city','city-test')]:
            receipt={'lot_id':lid,'version':d['version'],'organization_id':owner,'terms_hash':terms_hash(d),'decision':'approve','receipt_id':'api-'+owner}
            status,result=self.api.call('POST','/approvals',receipt,token=token)
            self.assertEqual(status,200,result)
            self.assertEqual(result['committed'],owner=='city')
        self.assertTrue(self.api.call('GET','/requests/TEST1')[1]['pickups'])

    def test_condition_check_requires_own_human_and_new_version(self):
        offer=copy.deepcopy(self.f['surplus_offers'][0]); offer['items'][0]['condition_doubt']='inspect bruising'
        status,created=self.api.call('POST','/surplus-offers',offer,token='donor-test')
        self.assertEqual(status,201)
        lot=self.e.records.get('lot',created['lot_id'])
        body={'organization_id':'market','version':lot['draft']['version'],'produce_id':'apples','condition_grade':'use_soon','usable_until':'2026-10-13T22:00:00-07:00','reason':'Donor inspected; use today'}
        target='/lots/'+created['lot_id']+'/condition-checks'
        self.assertEqual(self.api.call('POST',target,body,token='city-test')[0],401)
        status,result=self.api.call('POST',target,body,token='donor-test')
        self.assertEqual(status,200,result)
        self.assertFalse(result['committed'])
        self.assertGreater(result['version'],body['version'])

    def test_release_reassigns_without_exceeding_fair_share(self):
        f=fixture(); f['household_replies']=[]
        f['requests'].append({**f['requests'][0],'request_code':'TEST2'})
        records=Records(); run_fixture(f,records=records)
        e=Engine(f,records); api=API(e,clock=lambda:'2026-10-13T18:00:00-07:00')
        old=next(p for p in records.all('pickup') if p['request_code']=='TEST1')
        status,result=api.call('POST','/pickups/'+old['pickup_id']+'/release',{'request_code':'TEST1'})
        self.assertEqual(status,200,result)
        self.assertEqual(sum(p['pounds'] for p in records.all('pickup') if p['request_code']=='TEST2' and p['status']=='committed'),4)
        self.assertEqual(sum(p['pounds'] for p in records.all('pickup') if p['status']=='committed'),4)



class EvaluationTests(unittest.TestCase):
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


if __name__=='__main__': unittest.main()
