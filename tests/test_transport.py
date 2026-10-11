import copy
import threading
import unittest
from http.server import ThreadingHTTPServer
from harvestnet_platform.transport import Receiver, InProcess, A2ATransport, ORGANIZATIONS, handler_for
from harvestnet_platform.directory import LocalDirectory, record_info
from harvestnet_platform.systems import Systems
from harvestnet_platform.http import request_json
from urllib.error import HTTPError


def envelope(seq=1, actor='donor', event='transport-fixture'):
    return {'event_id': event, 'sequence': seq, 'turn': actor,
            'input': {'turn': actor, 'draft': {'version': 1, 'terms': {}}, 'facts': {}}}


class TransportTests(unittest.TestCase):
    def test_same_order_and_moves_over_real_http_and_in_process(self):
        servers, threads, endpoints, receivers = [], [], {}, {}
        local = InProcess({org: Receiver(org) for org in ORGANIZATIONS})
        try:
            for org in ORGANIZATIONS:
                receiver = Receiver(org)
                server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(receiver, 'test-transport', 'http://localhost'))
                servers.append(server)
                receivers[org] = receiver
                endpoints[org] = f'http://127.0.0.1:{server.server_port}'
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                threads.append(thread)
            network = A2ATransport(endpoints, 'test-transport')
            for seq, actor in enumerate(ORGANIZATIONS, 1):
                message = envelope(seq, actor)
                expected = local.broadcast(message)
                self.assertEqual(network.broadcast(message), expected)
                self.assertEqual(network.broadcast(message), expected)  # identical retry
            for org in ORGANIZATIONS:
                self.assertEqual(receivers[org].observed_order('transport-fixture'), [1,2,3,4,5])
            with self.assertRaises(HTTPError) as failure:
                request_json(endpoints['city'] + '/commit', {'version': 1}, token='test-transport')
            self.assertEqual(failure.exception.code, 405)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()

    def test_conflicts_gaps_unauthorized_commit_and_advocate_vote_fail(self):
        receiver = Receiver('donor')
        with self.assertRaises(ValueError):
            receiver.receive(envelope(2))
        receiver.receive(envelope())
        changed = envelope()
        changed['input']['draft']['version'] = 2
        with self.assertRaises(ValueError):
            receiver.receive(changed)
        for action, org in [('commit', 'donor'), ('accept', 'advocate')]:
            policy = lambda organization, data: {'organization_id': organization, 'version': 1, 'action': action, 'reason': 'Unauthorized'}
            with self.assertRaises(ValueError):
                Receiver(org, policy).receive(envelope(actor=org))

    def test_discovery_filters_cold_space_hours_and_changed_state(self):
        systems = Systems()
        directory = LocalDirectory(systems, {org: 'http://localhost' for org in ORGANIZATIONS})
        query = dict(min_cold_lb=100, pickup_at='2026-10-12T02:00:00Z')
        result = directory.search(**query)
        self.assertEqual(result['mode'], 'local_directory_fallback')
        self.assertEqual([record_info(r)['organization_id'] for r in result['records']], ['city','eastside'])
        systems.switch('city', True)
        self.assertEqual([record_info(r)['organization_id'] for r in directory.search(**query)['records']], ['eastside'])
        equivalent = dict(min_cold_lb=100, pickup_at='2026-10-11T19:00:00-07:00')
        self.assertEqual(len(directory.search(**equivalent)['records']),1)
