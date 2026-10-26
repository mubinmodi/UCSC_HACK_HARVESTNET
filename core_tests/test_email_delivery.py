"""The email outbox never stores an address and never auto-retries an uncertain send."""
from types import SimpleNamespace
import unittest

from harvestnet_core.api import API
from harvestnet_core.email_delivery import EmailDispatcher, post_webhook
from harvestnet_core.records import Records


WINDOW={'start':'2026-10-13T18:00:00-07:00','end':'2026-10-13T20:00:00-07:00'}


def setup_pickup(*, status='committed', version=1, email='test@example.org', queue=True):
    records=Records()
    if queue:
        records.enable_email_outbox()
    pickup={'pickup_id':'pk1','lot_id':'lot1','request_code':'TEST1','food_bank_id':'city',
            'food_bank_name':'City Food Bank','status':status,'version':version,'window':WINDOW,
            'items':[{'produce_id':'apples','pounds':4}],'pounds':4}
    with records.transaction():
        records.put('request','TEST1',{'request_code':'TEST1','language':'en','snap':'no'})
        if email:
            records.put('email','TEST1',{'email':email})
        records.put('pickup','pk1',pickup)
        records.event('lot1','2026-10-13T15:00:00-07:00',
                      'pickup_released' if status=='released' else 'pickup_notice',
                      {'pickup_id':'pk1','version':version,
                       **({'source':'household'} if status=='released' else {})})
    api=SimpleNamespace(records=records,household_page_url='https://harvestnet.example/household/',
                        item_name=lambda produce_id,language: 'Apples')
    return api


def dispatcher(api, sent, *, allow=('test@example.org',)):
    return EmailDispatcher(api,pickup_webhook='https://n8n.example/pickup',
                           release_webhook='https://n8n.example/released',token='test-token',
                           allowed_recipients=allow,send=lambda url,token,notice:sent.append((url,token,notice)))


class EmailDeliveryTests(unittest.TestCase):
    def test_enabling_email_does_not_send_historical_pickup_events(self):
        api=setup_pickup(queue=False)
        self.assertEqual(api.records.all('email_outbox'),[])
        api.records.enable_email_outbox()
        api.records.event('lot1','2026-10-13T16:00:00-07:00','pickup_notice',
                          {'pickup_id':'pk1','version':1})
        self.assertEqual(len(api.records.all('email_outbox')),1)
        api.records.close()

    def test_event_and_outbox_roll_back_together(self):
        records=Records()
        records.enable_email_outbox()
        with self.assertRaises(RuntimeError):
            with records.transaction():
                records.event('lot1','2026-10-13T16:00:00-07:00','pickup_notice',
                              {'pickup_id':'pk1','version':1})
                raise RuntimeError('simulate process failure before commit')
        self.assertEqual(records.events('lot1'),[])
        self.assertEqual(records.all('email_outbox'),[])
        records.close()

    def test_committed_pickup_is_sent_once_without_storing_address_in_outbox(self):
        api=setup_pickup()
        sent=[]
        worker=dispatcher(api,sent)
        self.assertEqual(worker.dispatch_pending()['sent'],1)
        self.assertEqual(worker.dispatch_pending()['sent'],0)
        self.assertEqual(len(sent),1)
        self.assertEqual(sent[0][2]['kind'],'pickup_ready')
        self.assertEqual(sent[0][2]['to'],'test@example.org')
        self.assertEqual(api.records.all('email_outbox')[0]['status'],'sent')
        self.assertNotIn('test@example.org',str(api.records.events('lot1')))
        self.assertNotIn('test@example.org',str(api.records.all('email_outbox')))
        api.records.close()

    def test_no_address_and_outside_test_allowlist_are_skipped(self):
        for email in (None,'someone-else@example.org'):
            with self.subTest(email=email):
                api=setup_pickup(email=email)
                sent=[]
                self.assertEqual(dispatcher(api,sent).dispatch_pending()['skipped'],1)
                self.assertEqual(sent,[])
                api.records.close()

    def test_stale_pickup_notice_is_never_sent(self):
        api=setup_pickup()
        pickup=api.records.get('pickup','pk1')
        pickup['version']=2
        api.records.put('pickup','pk1',pickup)
        sent=[]
        self.assertEqual(dispatcher(api,sent).dispatch_pending()['skipped'],1)
        self.assertEqual(sent,[])
        api.records.close()

    def test_release_thank_you_only_after_release(self):
        api=setup_pickup(status='released')
        sent=[]
        self.assertEqual(dispatcher(api,sent).dispatch_pending()['sent'],1)
        self.assertEqual(sent[0][2]['kind'],'pickup_released')
        self.assertNotIn('TEST1',str(sent[0][2]))
        api.records.close()

    def test_cooler_failure_release_does_not_queue_household_thank_you(self):
        api=setup_pickup(status='released',queue=False)
        api.records.enable_email_outbox()
        api.records.event('lot1','2026-10-13T16:00:00-07:00','pickup_released',
                          {'pickup_id':'pk1','pounds':4,'reason':'cooler failure: no safe pathway'})
        self.assertEqual(api.records.all('email_outbox'),[])
        api.records.close()

    def test_ambiguous_failure_is_recorded_without_an_automatic_retry(self):
        api=setup_pickup()
        attempts=[]
        def fail(url,token,notice):
            attempts.append(notice)
            raise TimeoutError()
        worker=EmailDispatcher(api,pickup_webhook='https://n8n.example/pickup',
                               release_webhook='https://n8n.example/released',token='test-token',
                               allowed_recipients=['test@example.org'],send=fail)
        self.assertEqual(worker.dispatch_pending()['uncertain'],1)
        self.assertEqual(worker.dispatch_pending()['uncertain'],0)
        self.assertEqual(len(attempts),1)
        self.assertEqual(api.records.all('email_outbox')[0]['status'],'uncertain')
        api.records.close()

    def test_webhook_goes_through_the_one_json_client_and_needs_a_sent_confirmation(self):
        from unittest import mock
        notice={'to':'test@example.org'}
        with mock.patch('harvestnet_core.email_delivery.request_json',return_value={'sent':True}) as client:
            post_webhook('https://n8n.example/pickup','test-token',notice)
        client.assert_called_once_with('https://n8n.example/pickup',notice,token='test-token',timeout=10,method='POST')
        with mock.patch('harvestnet_core.email_delivery.request_json',return_value={'sent':False}):
            with self.assertRaises(ValueError):
                post_webhook('https://n8n.example/pickup','test-token',notice)

    def test_webhook_rejects_insecure_public_url_before_network(self):
        with self.assertRaises(ValueError):
            post_webhook('http://n8n.example/pickup','test-token',{'to':'test@example.org'})


if __name__=='__main__':
    unittest.main()
