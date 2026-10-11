import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from harvestnet_platform.approvals import ApprovalStore, CoreAPI, StaleApproval, handler_for, pickup_message
from harvestnet_platform.http import request_json


class ApprovalTests(unittest.TestCase):
    def test_no_answer_no_approval_new_terms_invalidate_old_decisions(self):
        store = ApprovalStore(clock=lambda: 1000)
        links = store.request('lot', 1, {'apples_lb': 300}, ['donor','city'])
        self.assertEqual(store.approved_organizations('lot'), [])
        link = links[0]
        store.view(link['token'])  # GET/read has no side effect
        self.assertEqual(store.approved_organizations('lot'), [])
        receipt = store.decide(link['token'], 'approve', 1, link['terms_hash'], True)
        self.assertEqual(store.decide(link['token'], 'approve', 1, link['terms_hash'], True), receipt)
        self.assertEqual(store.approved_organizations('lot'), ['donor'])
        store.request('lot', 2, {'apples_lb': 250}, ['donor','city'])
        self.assertEqual(store.approved_organizations('lot'), [])
        with self.assertRaises(StaleApproval):
            store.decide(link['token'], 'approve', 1, link['terms_hash'], True)

    def test_expired_modified_and_implicit_approvals_fail(self):
        now = [1000]
        store = ApprovalStore(clock=lambda: now[0])
        link = store.request('lot', 1, {'romaine_lb': 200}, ['city'])[0]
        with self.assertRaises(ValueError):
            store.decide(link['token'], 'approve', 1, link['terms_hash'], False)
        with self.assertRaises(StaleApproval):
            store.decide(link['token'], 'approve', 1, 'different-terms', True)
        with self.assertRaises(ValueError):
            store.request('other', 1, {'romaine_lb': 200}, ['advocate'])
        now[0] = 2000
        with self.assertRaises(StaleApproval):
            store.view(link['token'])

    def test_pickup_text_only_committed_and_verified_snap_tips(self):
        notice = {'committed': True, 'food_bank': 'Rural food bank', 'items': [{'name':'apples','pounds':8}],
                  'window': {'start':'18:00','end':'20:00'}, 'request_code':'ABCD', 'pickup_id':'pickup-1',
                  'version':2, 'release_url':'https://demo.example/release', 'snap':'yes',
                  'market': {'name':'Example market', 'verified':True, 'nearby':True,
                             'source_url':'https://example.org/verified', 'verified_at':'2026-10-10T00:00:00Z'}}
        now = datetime(2026,10,11,tzinfo=timezone.utc)
        text = pickup_message(notice, now=now)
        for part in ('Rural food bank','8 lb apples','18:00','20:00','ABCD','Market Match'):
            self.assertIn(part,text)
        for snap in ('no','not_said',None):
            self.assertNotIn('Market Match',pickup_message({**notice,'snap':snap},now=now))
        self.assertNotIn('Market Match',pickup_message({**notice,'market':{**notice['market'],'verified':False}},now=now))
        self.assertNotIn('Market Match',pickup_message({**notice,'market':{**notice['market'],'verified_at':'2025-01-01T00:00:00Z'}},now=now))
        with self.assertRaises(ValueError):
            pickup_message({**notice,'committed':False},now=now)

    def test_release_calls_core_operation_with_pickup_token(self):
        core = CoreAPI('https://core.example','broad-service-token')
        with patch('harvestnet_platform.approvals.request_json', return_value={'released':True}) as call:
            self.assertTrue(core.release('ABCD','pickup-1','pickup-token')['released'])
            self.assertEqual(call.call_args.args[0], 'https://core.example/pickups/pickup-1/release')
            self.assertEqual(call.call_args.kwargs['token'],'pickup-token')
        self.assertFalse(CoreAPI().release('ABCD','pickup-1','token')['released'])

    def test_http_human_decision_and_stale_callback(self):
        store = ApprovalStore()
        server = ThreadingHTTPServer(('127.0.0.1',0),handler_for(store,CoreAPI(),'events-token','http://localhost'))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(HTTPError):
                request_json(base+'/approval-requests',{'event_id':'lot','version':1,'terms':{'lb':8},'organizations':['donor']})
            result = request_json(base+'/approval-requests',{'event_id':'lot','version':1,'terms':{'lb':8},'organizations':['donor']},token='events-token')
            link = result['requests'][0]
            token = link['decision_url'].split('token=')[1]
            receipt = request_json(base+'/human/decision',{'token':token,'decision':'approve','version':1,'terms_hash':link['terms_hash'],'human_confirmed':True})
            self.assertFalse(receipt['committed'])
            self.assertEqual(receipt['mode'],'local_approval_fallback')
            request_json(base+'/approval-requests',{'event_id':'lot','version':2,'terms':{'lb':7},'organizations':['donor']},token='events-token')
            with self.assertRaises(HTTPError) as stale:
                request_json(base+'/human/decision',{'token':token,'decision':'approve','version':1,'terms_hash':link['terms_hash'],'human_confirmed':True})
            self.assertEqual(stale.exception.code,409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
