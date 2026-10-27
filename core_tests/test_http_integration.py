import json
import threading
import unittest
import urllib.request
from pathlib import Path

import platform_source  # noqa: F401  (Lane C on the import path)

from harvestnet_core.api import API
from harvestnet_core.engine import Engine,run_fixture
from harvestnet_core.server import make_server
from harvestnet_core.records import Records
from test_core import fixture


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.e=Engine(fixture())
        self.api=API(self.e,clock=lambda:'2026-10-13T12:00:00-07:00',staff_tokens={'market':'test-market','city':'test-city'})
        self.server=make_server(self.api,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.e.records.close()
    def request(self,method,path,data=None,token=None):
        headers={'Content-Type':'application/json'}
        if token: headers['Authorization']='Bearer '+token
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        with urllib.request.urlopen(req,timeout=5) as response: return response.status,json.load(response)

    def test_browser_style_create_and_preview_contract(self):
        form={k:fixture()['requests'][0][k] for k in ('household_size','pickup_windows','limited_fridge','neighborhood','cant_eat','snap','language')}
        status,preview=self.request('POST','/requests/preview',form)
        self.assertFalse(preview['saved'])
        status,r=self.request('POST','/requests',{**form,'consent':True})
        self.assertEqual(status,201)
        status,r=self.request('GET','/requests/'+r['request_code'])
        self.assertEqual(r['fair_share_lb'],4);self.assertEqual(r['pickups'],[])

    def test_actual_lane_c_human_capability_relay_reaches_core(self):
        from harvestnet_platform.approvals import ApprovalStore,CoreAPI
        f=fixture();f['humans']=[]
        run_fixture(f,records=self.e.records)
        lot=self.e.records.all('lot')[0];d=lot['draft']
        store=ApprovalStore()
        links=store.request(d['lot_id'],d['version'],d,['market','city'])
        for link in links:
            record=store.decide(link['token'],'approve',link['version'],link['terms_hash'],True)
            client=CoreAPI(self.base,'test-market' if link['organization_id']=='market' else 'test-city')
            result=client.decision(record)
            self.assertEqual(result['committed'],link['organization_id']=='city')
        self.assertTrue(self.e.records.all('pickup'))
        store.db.close()

    def test_real_mixed_batch_outcomes_identical_over_five_a2a_hosts(self):
        from http.server import ThreadingHTTPServer
        from harvestnet_platform.transport import ORGANIZATIONS,Receiver,A2ATransport,handler_for
        from harvestnet_platform.join import compare_fixture
        from harvestnet_platform.transport_auth import Signer,Verifier,generate_keys,pair_key
        from harvestnet_core.join_adapter import harness,policy
        keys=generate_keys()  # throwaway per-sender transport keys for this test
        def verifier(org): return Verifier(org,{s:pair_key(k,org) for s,k in keys.items() if s!=org})
        servers=[];threads=[];endpoints={}
        try:
            for org in ORGANIZATIONS:
                server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(Receiver(org,policy),verifier(org),'http://localhost'))
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                servers.append(server);threads.append(thread)
                endpoints[org]='http://127.0.0.1:'+str(server.server_port)
            f=json.loads(Path('core_fixtures/normal-afternoon.json').read_text())
            report=compare_fixture(f,harness,policy,A2ATransport(endpoints,Signer('core',keys['core'])))
            self.assertEqual(report['status'],'identical_outcomes')
            self.assertTrue(report['commitments'])
            self.assertTrue(all(report['rule_checks'].values()))
        finally:
            for server in servers: server.shutdown();server.server_close()
            for thread in threads: thread.join()
