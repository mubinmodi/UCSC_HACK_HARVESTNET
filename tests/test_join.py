import copy
import threading
import unittest
from http.server import ThreadingHTTPServer
from harvestnet_platform.transport import ORGANIZATIONS, Receiver, A2ATransport, handler_for, role_of
from harvestnet_platform.join import compare_fixture, require_outcomes, REQUIRED_CHECKS, MoveBridge
from test_transport import signer, verifier


def fixture_policy(org, data):
    # Synthetic test policy, not Lane B implementation.
    return {'organization_id':org,'version':data['draft']['version'],'action':'accept',
            'reason':'Synthetic fixture calculation passed; this is not a human approval.'}


def fixture_harness(fixture, move):
    moves = [move(org,{'role':role_of(org),'draft':{'version':1,'terms':fixture['terms']},'facts':{},
                       'turn':{'organization_id':org,'number':n,'now':'2026-10-13T12:00:00-07:00','accepted_by':[]}})
             for n,org in enumerate(('market','city','rural','eastside'),1)]
    # The harness fixture includes explicit human approvals, separately from moves.
    committed = all(m['action']=='accept' for m in moves) and fixture['human_approvals'] == ['market','city','rural','eastside']
    return {'commitments':[{'version':1,'terms':fixture['terms']}] if committed else [],
            'pathways':fixture['pathways'], 'rule_checks':{key:True for key in REQUIRED_CHECKS}}


class JoinTests(unittest.TestCase):
    def test_synthetic_mixed_batch_seam_has_identical_http_outcomes(self):
        servers, threads, endpoints = [], [], {}
        try:
            for org in ORGANIZATIONS:
                server = ThreadingHTTPServer(('127.0.0.1',0),handler_for(Receiver(org,fixture_policy),verifier(org),'http://localhost'))
                thread = threading.Thread(target=server.serve_forever,daemon=True)
                thread.start()
                servers.append(server)
                threads.append(thread)
                endpoints[org] = f'http://127.0.0.1:{server.server_port}'
            fixture = {'terms':{'apples':{'rural':250,'eastside':50},'romaine':{'city':200},'potatoes':{'rural':400}},
                       'human_approvals':['market','city','rural','eastside'],
                       'pathways':[{'item':'apples','pounds':300},{'item':'romaine','pounds':200},{'item':'potatoes','pounds':400}]}
            report = compare_fixture(fixture,fixture_harness,fixture_policy,A2ATransport(endpoints,signer()))
            self.assertEqual(report['status'],'identical_outcomes')
            self.assertEqual(report['network_mode'],'a2a_jsonrpc')
            fixture['human_approvals'] = []
            self.assertEqual(compare_fixture(fixture,fixture_harness,fixture_policy,A2ATransport(endpoints,signer()))['commitments'],[])
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()

    def test_mismatched_outcomes_or_missing_rule_checks_fail(self):
        with self.assertRaises(ValueError):
            require_outcomes({'commitments':[],'pathways':[],'rule_checks':{}})
        checks = {key:True for key in REQUIRED_CHECKS}
        checks['no_auto_commit'] = False
        with self.assertRaises(ValueError):
            require_outcomes({'commitments':[],'pathways':[],'rule_checks':checks})
        calls = []
        def inconsistent(_fixture,_move):
            calls.append(1)
            return {'commitments':[],'pathways':[len(calls)],'rule_checks':{key:True for key in REQUIRED_CHECKS}}
        with self.assertRaises(ValueError):
            compare_fixture({},inconsistent,fixture_policy,object())

    def test_partial_delivery_requires_same_turn_retry(self):
        class Partial:
            def __init__(self):
                self.calls=0
            def broadcast(self,envelope):
                self.calls+=1
                if self.calls==1:
                    raise OSError('partial outage')
                return [{'organization_id':'market','move':fixture_policy('market',envelope['input'])}]
        bridge = MoveBridge(Partial())
        data = {'role':'donor','draft':{'version':1,'terms':{}},'facts':{},
                'turn':{'organization_id':'market','number':1,'now':'2026-10-13T12:00:00-07:00','accepted_by':[]}}
        with self.assertRaises(OSError):
            bridge('market',data)
        with self.assertRaises(ValueError):
            bridge('market',{**data,'draft':{'version':2}})
        self.assertEqual(bridge('market',data)['action'],'accept')
