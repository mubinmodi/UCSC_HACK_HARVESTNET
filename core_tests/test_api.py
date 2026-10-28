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
        status,r=self.api.call('POST','/requests',{**self.form,'consent':True,'email':'household@example.invalid'})
        self.assertEqual(status,201); self.assertEqual(r['fair_share_lb'],4)
        self.assertNotIn('email',r); self.assertIs(r['emails'],True)
        self.assertTrue(self.e.records.get('email',r['request_code']))
        self.now='2026-10-20T12:00:00-07:00'
        self.assertEqual(self.api.call('GET','/requests/'+r['request_code'])[0],404)
        self.assertEqual(self.e.records.all('email'),[])
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


    def test_the_approvals_credential_records_only_a_review_link_decision(self):
        # Test placeholder credential; the bridge holds this instead of every staff token.
        bridge='approvals-test-placeholder-credential'
        api=API(self.e,clock=lambda:self.now,staff_tokens={'market':'donor-test','city':'city-test'},approvals_token=bridge)
        status,created=api.call('POST','/surplus-offers',copy.deepcopy(self.f['surplus_offers'][0]),token='donor-test')
        self.assertEqual(status,201,created)
        lid=created['lot_id']; d=self.e.records.get('lot',lid)['draft']
        receipt={'lot_id':lid,'version':d['version'],'organization_id':'market','terms_hash':terms_hash(d),'decision':'approve'}
        self.assertEqual(api.call('POST','/approvals',receipt,token=bridge)[0],401)  # no link receipt ID
        self.assertEqual(api.call('POST','/approvals',{**receipt,'receipt_id':'link-receipt-0001'},token=bridge)[0],200)
        # Still bound to the exact current version and terms.
        self.assertEqual(api.call('POST','/approvals',{**receipt,'organization_id':'city','terms_hash':'sha256:'+'0'*64,
                                                       'receipt_id':'link-receipt-0002'},token=bridge)[0],409)
        # No staff action: dashboards, counters, offers, status and the approvals list all refuse it.
        counter={'organization_id':'city','version':d['version'],'amendment':{'kind':'set_pounds','produce_id':'apples','food_bank_id':'city','pounds':3},'reason':'x'}
        for method,target,body in (('GET','/food-banks/city/dashboard',None),('GET','/approvals?organization_id=market',None),
                                   ('POST','/lots/'+lid+'/counters',counter),('POST','/surplus-offers',copy.deepcopy(self.f['surplus_offers'][0])),
                                   ('PUT','/food-banks/city/status',{'cooler':{'status':'failed'}})):
            with self.subTest(target=target):
                self.assertEqual(api.call(method,target,body,token=bridge)[0],401)
        for bad in ('donor-test','short'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                API(self.e,staff_tokens={'market':'donor-test'},approvals_token=bad)


    def test_counter_is_processed_on_owner_turn_and_invalidates_approval(self):
        status,created=self.api.call('POST','/surplus-offers',copy.deepcopy(self.f['surplus_offers'][0]),token='donor-test')
        self.assertEqual(status,201,created)
        lid=created['lot_id']; d=self.e.records.get('lot',lid)['draft']
        receipt={'lot_id':lid,'version':d['version'],'organization_id':'market','terms_hash':terms_hash(d),'decision':'approve'}
        self.assertEqual(self.api.call('POST','/approvals',receipt,token='donor-test')[0],200)
        counter={'organization_id':'city','version':d['version'],'amendment':{'kind':'set_pounds','produce_id':'apples','food_bank_id':'city','pounds':3},'reason':'Owner requests a smaller allocation'}
        status,result=self.api.call('POST','/lots/'+lid+'/counters',counter,token='city-test')
        self.assertEqual(status,202,result)
        lot=self.e.records.get('lot',lid)
        self.assertGreater(lot['draft']['version'],d['version'])
        self.assertEqual(lot['approvals'],{})
        self.assertEqual(self.e.records.all('queued_move'),[])
        self.assertEqual(self.api.call('POST','/approvals',receipt,token='donor-test')[0],409)
        self.assertEqual(self.api.call('GET','/requests/TEST1')[1]['pickups'],[])


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


