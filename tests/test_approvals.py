import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
import json
import os
from harvestnet_platform.approvals import ApprovalStore, CoreAPI, StaleApproval, email_address, handler_for, pickup_email
from harvestnet_platform.http import JsonHandler, request_json


class ApprovalTests(unittest.TestCase):
    def test_no_answer_no_approval_new_terms_invalidate_old_decisions(self):
        store = ApprovalStore(clock=lambda: 1000)
        links = store.request('lot', 1, {'apples_lb': 300}, ['market','city'])
        self.assertEqual(store.approved_organizations('lot'), [])
        link = links[0]
        store.view(link['token'])  # GET/read has no side effect
        self.assertEqual(store.approved_organizations('lot'), [])
        receipt = store.decide(link['token'], 'approve', 1, link['terms_hash'], True)
        self.assertEqual(store.decide(link['token'], 'approve', 1, link['terms_hash'], True), receipt)
        self.assertEqual(store.approved_organizations('lot'), ['market'])
        store.request('lot', 2, {'apples_lb': 250}, ['market','city'])
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
        now[0] = 1000 + 3600  # the default lifetime is one hour (APPROVAL_LINK_TTL_SECONDS)
        with self.assertRaises(StaleApproval):
            store.view(link['token'])

    def test_pickup_email_only_committed_and_verified_snap_tips(self):
        notice = {'committed': True, 'food_bank': 'Rural food bank', 'items': [{'name':'apples','pounds':8}],
                  'window': {'start':'18:00','end':'20:00'}, 'request_code':'ABCD', 'pickup_id':'pickup-1',
                  'version':2, 'release_url':'https://demo.example/household/#pickup=pickup-1&code=ABCD&lang=en', 'snap':'yes',
                  'to': 'household@example.invalid',
                  'market': {'name':'Example market', 'verified':True, 'nearby':True,
                             'source_url':'https://example.org/verified', 'verified_at':'2026-10-10T00:00:00Z'}}
        now = datetime(2026,10,11,tzinfo=timezone.utc)
        mail = pickup_email(notice, now=now)
        self.assertEqual((mail['to'], mail['kind'], mail['language']), ('household@example.invalid', 'pickup_ready', 'en'))
        self.assertEqual(mail['subject'], 'HarvestNet: your produce is ready at Rural food bank')
        for part in ('Rural food bank','8 lb apples','18:00','20:00','ABCD','Market Match', "Can't make it?", notice['release_url']):
            self.assertIn(part,mail['text'])
        self.assertNotIn('Reply', mail['text'])  # nothing to reply to: the link does it
        for snap in ('no','not_said',None):
            self.assertNotIn('Market Match',pickup_email({**notice,'snap':snap},now=now)['text'])
        self.assertNotIn('Market Match',pickup_email({**notice,'market':{**notice['market'],'verified':False}},now=now)['text'])
        self.assertNotIn('Market Match',pickup_email({**notice,'market':{**notice['market'],'verified_at':'2025-01-01T00:00:00Z'}},now=now)['text'])
        with self.assertRaises(ValueError):
            pickup_email({**notice,'committed':False},now=now)

    def test_spanish_pickup_email_uses_the_same_facts(self):
        """Ticket #6: a Spanish household gets its email in Spanish; the numbers are unchanged."""
        notice = {'committed': True, 'language': 'es', 'food_bank': 'Rural food bank', 'items': [{'name':'manzanas','pounds':8},{'name':'papas','pounds':4}],
                  'window': {'start':'2026-10-14T18:00:00-07:00','end':'2026-10-14T20:00:00-07:00'}, 'request_code':'ABCD', 'pickup_id':'pickup-1',
                  'version':2, 'release_url':'https://demo.example/household/#pickup=pickup-1&code=ABCD&lang=es', 'to': 'hogar@example.invalid'}
        mail = pickup_email(notice)
        self.assertEqual(mail['subject'], 'HarvestNet: sus productos están listos en Rural food bank')
        for part in ('8 lb de manzanas y 4 lb de papas','Rural food bank','miércoles 14 de octubre, de 6 p. m. a 8 p. m.','Su código: ABCD',
                     '¿No puede ir?', 'No puedo ir', notice['release_url'], 'se borra con su solicitud después de 7 días'):
            self.assertIn(part,mail['text'])
        self.assertNotIn('Responda', mail['text'])
        english = pickup_email({**notice, 'language': 'en'})['text']
        self.assertIn('8 lb manzanas and 4 lb papas', english)
        self.assertIn('Wednesday, October 14, 6 pm to 8 pm', english)

    def test_changed_and_released_emails(self):
        changed = {'kind': 'pickup_changed', 'committed': True, 'language': 'en', 'food_bank': 'Eastside food bank',
                   'items': [{'name': 'romaine lettuce', 'pounds': 4}], 'window': {'start': '2026-10-14T01:00:00Z', 'end': '2026-10-14T03:00:00Z'},
                   'request_code': 'C4N6', 'pickup_id': 'pk-1', 'version': 4, 'reply_expected': True,
                   'release_url': 'https://demo.example/household/#pickup=pk-1&code=C4N6&lang=en', 'to': 'c4n6@example.invalid'}
        mail = pickup_email(changed)
        self.assertEqual(mail['subject'], 'HarvestNet: your pickup changed')
        self.assertIn('Your pickup changed. It is now at Eastside food bank.', mail['text'])
        self.assertIn("This isn't a food bank you chose.", mail['text'])
        self.assertNotIn("This isn't a food bank you chose.", pickup_email({**changed, 'reply_expected': False})['text'])
        thanks = pickup_email({'kind': 'pickup_released', 'released': True, 'pickup_id': 'pk-1', 'language': 'es', 'to': 'c4n6@example.invalid'})
        self.assertEqual(thanks['subject'], 'HarvestNet: gracias por avisarnos')
        self.assertIn('Su porción pasará a otra familia.', thanks['text'])
        with self.assertRaises(ValueError):
            pickup_email({'kind': 'pickup_released', 'released': False, 'pickup_id': 'pk-1', 'to': 'c4n6@example.invalid'})
        with self.assertRaises(ValueError):
            pickup_email({**changed, 'kind': 'sms'})

    def test_pickup_email_refuses_bad_addresses_and_header_injection(self):
        notice = {'committed': True, 'food_bank': 'Rural food bank', 'items': [{'name':'apples','pounds':8}],
                  'window': {'start':'18:00','end':'20:00'}, 'request_code':'ABCD', 'pickup_id':'pickup-1',
                  'version':2, 'release_url':'https://demo.example/household/#pickup=pickup-1&code=ABCD&lang=en', 'to': 'a@example.invalid'}
        self.assertEqual(email_address(' A@Example.INVALID '), 'A@example.invalid')
        for to in (None, '', '+18315550101', 'a@b', 'a@example.invalid\r\nBcc: b@example.invalid', 'a@example.invalid, b@example.invalid'):
            with self.subTest(to=to), self.assertRaises(ValueError) as refused:
                pickup_email({**notice, 'to': to})
            if to:
                self.assertNotIn(to, str(refused.exception))
        for field, value in (('food_bank', 'Rural\r\nBcc: b@example.invalid'), ('release_url', 'javascript:alert(1)'),
                             ('items', [{'name': 'apples\nBcc: x', 'pounds': 8}])):
            with self.subTest(field=field), self.assertRaises(ValueError):
                pickup_email({**notice, field: value})

    def test_n8n_only_relays_an_explicit_bound_human_receipt(self):
        store = ApprovalStore()
        link = store.request('lot',1,{'lb':8},['market'])[0]
        record = store.decide(link['token'],'approve',1,link['terms_hash'],True)
        core = CoreAPI(decision_webhook='https://n8n.example/webhook/human-decision',webhook_token='relay-token')
        with patch('harvestnet_platform.approvals.request_json',return_value={'status':'recorded'}) as call:
            core.decision(record)
            payload = call.call_args.args[1]
            self.assertEqual(payload['receipt_id'],record['receipt_id'])
            self.assertEqual(payload['terms_hash'],link['terms_hash'])
            self.assertEqual(payload['decision'],'approve')
            self.assertNotIn('token',payload)
            self.assertEqual(call.call_args.kwargs['token'],'relay-token')

    def test_http_human_decision_and_stale_callback(self):
        store = ApprovalStore()
        server = ThreadingHTTPServer(('127.0.0.1',0),handler_for(store,CoreAPI(),'events-token','http://localhost'))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(HTTPError):
                request_json(base+'/approval-requests',{'lot_id':'lot','version':1,'terms':{'lb':8},'organizations':['market']})
            result = request_json(base+'/approval-requests',{'lot_id':'lot','version':1,'terms':{'lb':8},'organizations':['market']},token='events-token')
            link = result['requests'][0]
            token = link['decision_url'].split('token=')[1]
            receipt = request_json(base+'/human/decision',{'token':token,'decision':'approve','version':1,'terms_hash':link['terms_hash'],'human_confirmed':True})
            self.assertFalse(receipt['committed'])
            self.assertEqual(receipt['mode'],'local_approval_fallback')
            request_json(base+'/approval-requests',{'event_id':'lot','version':2,'terms':{'lb':7},'organizations':['market']},token='events-token')  # the core's change requests still say event_id
            with self.assertRaises(HTTPError) as stale:
                request_json(base+'/human/decision',{'token':token,'decision':'approve','version':1,'terms_hash':link['terms_hash'],'human_confirmed':True})
            self.assertEqual(stale.exception.code,409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_issued_review_link_can_be_emailed_without_exposing_recipient_in_response(self):
        store = ApprovalStore()
        handler = handler_for(store, CoreAPI(), 'events-token', 'https://demo.example',
                              approver_emails={'market':'mubinmodi@gmail.com'},
                              approval_webhook='https://n8n.example/webhook/approval',
                              webhook_token='outbound-token', test_recipients=['mubinmodi@gmail.com'])
        base, stop = serve(handler)
        try:
            with patch('harvestnet_platform.approvals.request_json', return_value={'sent':True}) as send:
                result = request_json(base+'/approval-requests',
                                      {'lot_id':'lot','version':1,'terms':{'lb':8},'organizations':['market']},
                                      token='events-token')
            link = result['requests'][0]
            self.assertEqual(link['email_delivery'],'sent')
            self.assertNotIn('mubinmodi@gmail.com',str(result))
            self.assertIn('/human/review?token=',link['decision_url'])
            self.assertEqual(send.call_args.args[0],'https://n8n.example/webhook/approval')
            self.assertEqual(send.call_args.args[1]['to'],'mubinmodi@gmail.com')
            self.assertEqual(send.call_args.kwargs['token'],'outbound-token')
        finally:
            stop()

    def test_approval_email_needs_an_explicit_test_recipient_allowlist(self):
        handler = handler_for(ApprovalStore(), CoreAPI(), 'events-token', 'https://demo.example',
                              approver_emails={'market':'staff@example.org'},
                              approval_webhook='https://n8n.example/webhook/approval',
                              webhook_token='outbound-token')
        base, stop = serve(handler)
        try:
            with patch('harvestnet_platform.approvals.request_json') as send:
                result = request_json(base+'/approval-requests',
                                      {'lot_id':'lot','version':1,'terms':{'lb':8},'organizations':['market']},
                                      token='events-token')
            self.assertEqual(result['requests'][0]['email_delivery'],'outside_test_allowlist')
            send.assert_not_called()
        finally:
            stop()


def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def stop():
        server.shutdown()
        server.server_close()
        thread.join()
    return f'http://127.0.0.1:{server.server_port}', stop


class FakeCore(JsonHandler):
    """A stand-in core: records each call, and answers with a scripted status."""
    calls, answers = [], []

    def do_POST(self):
        FakeCore.calls.append({'path': self.path, 'body': self.read_json(), 'auth': self.headers.get('Authorization')})
        status, body = FakeCore.answers.pop(0) if FakeCore.answers else (200, {'committed': False})
        self.send_json(status, body)


class ContractTests(unittest.TestCase):
    def setUp(self):
        FakeCore.calls, FakeCore.answers = [], []

    def test_decision_matches_record_approval_with_each_organizations_own_token(self):
        store = ApprovalStore()
        links = store.request('lot-market-1013', 3, {'lb': 8}, ['market', 'city'])
        core_url, stop = serve(FakeCore)
        try:
            core = CoreAPI(core_url, {'market': 'market-staff', 'city': 'city-staff'})
            for link in links:
                record = store.decide(link['token'], 'approve', 3, link['terms_hash'], True)
                core.decision(record)
            for call, org in zip(FakeCore.calls, ('market', 'city')):
                self.assertEqual(call['path'], '/approvals')
                self.assertEqual(set(call['body']), {'lot_id', 'version', 'organization_id', 'terms_hash', 'decision', 'receipt_id'})
                self.assertEqual(call['body']['lot_id'], 'lot-market-1013')
                self.assertEqual(call['body']['organization_id'], org)
                self.assertTrue(call['body']['terms_hash'].startswith('sha256:'))
                self.assertEqual(len(call['body']['terms_hash']), 71)
                self.assertEqual(call['auth'], f'Bearer {org}-staff')
            with self.assertRaises(ValueError):
                CoreAPI(core_url, {'market': 'market-staff'}).decision({**record, 'organization_id': 'city'})
            with self.assertRaises(ValueError):
                CoreAPI(core_url, {'market': 'same', 'city': 'same'})
        finally:
            stop()

    def test_core_credentials_come_from_a_per_organization_map(self):
        clear = {'CORE_API_URL': 'https://core.example', 'CORE_API_TOKENS': '', 'HARVESTNET_STAFF_TOKENS': '', 'CORE_API_TOKEN': ''}
        with patch.dict(os.environ, {**clear, 'CORE_API_TOKENS': '{"market":"m","city":"c"}'}):
            core = CoreAPI.from_env()
            self.assertEqual((core.token_for('market'), core.token_for('city')), ('m', 'c'))
        with patch.dict(os.environ, {**clear, 'HARVESTNET_STAFF_TOKENS': '{"market":"m2","rural":"r2"}'}):
            self.assertEqual(CoreAPI.from_env().token_for('rural'), 'r2')  # the core's own map works too
        with patch.dict(os.environ, {**clear, 'CORE_API_TOKENS': '["m"]'}), self.assertRaises(ValueError):
            CoreAPI.from_env()
        with patch.dict(os.environ, {**clear, 'CORE_API_TOKEN': 'one'}):
            self.assertEqual(CoreAPI.from_env().token_for('city'), 'one')  # legacy single token still starts
        with patch.dict(os.environ, {**clear, 'CORE_API_URL': ''}):
            self.assertIsNone(CoreAPI.from_env().base_url)

    def test_core_rejections_pass_through_with_their_own_status(self):
        store = ApprovalStore()
        core_url, stop_core = serve(FakeCore)
        bridge, stop_bridge = serve(handler_for(store, CoreAPI(core_url, {'market': 'market-staff'}), 'events', 'http://localhost'))
        try:
            for status, code in ((401, 'unauthorized'), (409, 'conflict')):
                FakeCore.answers.append((status, {'error': {'code': code, 'message': f'core says {code}'}}))
                link = store.request(f'lot-{status}', 1, {'lb': 8}, ['market'])[0]
                with self.assertRaises(HTTPError) as failure:
                    request_json(bridge + '/human/decision', {'token': link['token'], 'decision': 'approve', 'version': 1,
                                                              'terms_hash': link['terms_hash'], 'human_confirmed': True})
                self.assertEqual(failure.exception.code, status)
                body = json.loads(failure.exception.read())
                self.assertEqual(body['error']['code'], code)
                self.assertEqual(body['core_status'], status)
                self.assertFalse(body['committed'])
        finally:
            stop_bridge()
            stop_core()

    def test_link_lifetime_is_configurable_and_reported_in_iso_8601(self):
        store = ApprovalStore(clock=lambda: 1_791_900_000)
        link = store.request('lot', 1, {'lb': 8}, ['market'])[0]
        self.assertEqual(datetime.fromisoformat(link['expires_at']).timestamp(), 1_791_900_000 + 3600)
        self.assertTrue(link['expires_at'].endswith('+00:00'))
        with patch.dict(os.environ, {'APPROVAL_LINK_TTL_SECONDS': '7200'}):
            link = store.request('other', 1, {'lb': 8}, ['market'])[0]
            self.assertEqual(datetime.fromisoformat(link['expires_at']).timestamp(), 1_791_900_000 + 7200)
        link = store.request('third', 1, {'lb': 8}, ['market'], ttl=60)[0]
        self.assertEqual(datetime.fromisoformat(store.view(link['token'])['expires_at']).timestamp(), 1_791_900_000 + 60)
        for bad in (0, 86401, 'soon', True):
            with self.subTest(ttl=bad), self.assertRaises(ValueError):
                store.request('bad', 1, {'lb': 8}, ['market'], ttl=bad)

    def test_a_lost_or_expired_link_can_be_reissued_for_the_same_version(self):
        now = [1000]
        store = ApprovalStore(clock=lambda: now[0])
        first = {l['organization_id']: l for l in store.request('lot', 2, {'lb': 8}, ['market', 'city'], ttl=60)}
        with self.assertRaises(ValueError):  # a plain retry adds no links
            store.request('lot', 2, {'lb': 8}, ['market', 'city'])
        store.decide(first['market']['token'], 'approve', 2, first['market']['terms_hash'], True)
        now[0] = 2000  # city's link expired before its human opened it
        with self.assertRaises(StaleApproval):
            store.view(first['city']['token'])
        again = store.request('lot', 2, {'lb': 8}, ['city'], reissue=True)[0]
        self.assertEqual((again['version'], again['terms_hash']), (2, first['city']['terms_hash']))
        self.assertEqual(store.decide(again['token'], 'approve', 2, again['terms_hash'], True)['decision'], 'approve')
        # Reissuing replaces the old link: it stops working, the new one counts.
        store2 = ApprovalStore(clock=lambda: now[0])
        old = store2.request('lot', 1, {'lb': 8}, ['city'])[0]
        new = store2.request('lot', 1, {'lb': 8}, ['city'], reissue=True)[0]
        with self.assertRaises(StaleApproval) as replaced:
            store2.view(old['token'])
        self.assertIn('replaced', str(replaced.exception))
        store2.decide(new['token'], 'approve', 1, new['terms_hash'], True)
        self.assertEqual(store2.approved_organizations('lot'), ['city'])
        with self.assertRaises(ValueError):  # a decided link is final for its version
            store2.request('lot', 1, {'lb': 8}, ['city'], reissue=True)
        with self.assertRaises(StaleApproval):  # changed terms need a new version
            store2.request('lot', 1, {'lb': 9}, ['city'], reissue=True)

    def test_decide_accepts_the_contract_hash_and_the_earlier_bare_hex(self):
        store = ApprovalStore()
        link = store.request('lot', 1, {'lb': 8}, ['market'])[0]
        self.assertTrue(link['terms_hash'].startswith('sha256:'))
        bare = link['terms_hash'].removeprefix('sha256:')
        self.assertEqual(store.decide(link['token'], 'approve', 1, bare, True)['decision'], 'approve')

    def test_prepare_returns_one_email_and_keeps_nothing(self):
        store = ApprovalStore()
        bridge, stop = serve(handler_for(store, CoreAPI(), 'events', 'http://localhost'))
        notice = {'committed': True, 'food_bank': 'Rural food bank', 'items': [{'name': 'apples', 'pounds': 4}],
                  'window': {'start': '2026-10-14T18:00:00-07:00', 'end': '2026-10-14T20:00:00-07:00'},
                  'request_code': 'K7P4', 'pickup_id': 'pk-1013-0001', 'version': 3,
                  'release_url': 'https://households.example.invalid/household/#pickup=pk-1013-0001&code=K7P4&lang=en',
                  'to': 'k7p4@example.invalid'}
        try:
            with self.assertRaises(HTTPError) as unauthenticated:
                request_json(bridge + '/notifications/prepare', notice)
            self.assertEqual(unauthenticated.exception.code, 401)
            prepared = request_json(bridge + '/notifications/prepare', notice, token='events')
            self.assertEqual((prepared['to'], prepared['mode'], prepared['sent']), ('k7p4@example.invalid', 'prepared_email', False))
            self.assertIn('Wednesday, October 14, 6 pm to 8 pm', prepared['text'])
            self.assertIn(notice['release_url'], prepared['text'])
            # The SMS reply route is gone; there is nothing to reply to.
            with self.assertRaises(HTTPError) as gone:
                request_json(bridge + '/household/replies', {'From': '+18315550101', 'Body': "can't make it"}, token='events')
            self.assertEqual(gone.exception.code, 404)
            # The address is never stored here.
            dump = '\n'.join(store.db.iterdump())
            self.assertNotIn('k7p4@example.invalid', dump)
            self.assertNotIn('reply_bindings', dump)
        finally:
            stop()

    def test_approval_requests_carry_an_email_subject(self):
        store = ApprovalStore()
        bridge, stop = serve(handler_for(store, CoreAPI(), 'events', 'http://localhost'))
        try:
            issued = request_json(bridge + '/approval-requests', {'lot_id': 'lot-1', 'version': 2, 'terms': {'lb': 8}, 'organizations': ['city']}, token='events')
            link = issued['requests'][0]
            self.assertEqual(link['subject'], 'HarvestNet: review draft version 2 for lot lot-1')
            self.assertIn(link['decision_url'], link['message'])
        finally:
            stop()
