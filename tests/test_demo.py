import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from harvestnet_platform.demo import handler_for
from harvestnet_platform.approvals import ApprovalStore
from harvestnet_platform.systems import Systems
from harvestnet_platform.http import request_json


class DemoTests(unittest.TestCase):
    def test_offline_rehearsal_buttons_use_labeled_fallbacks(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),handler_for(Systems(),ApprovalStore(),'session-token','http://localhost'))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base) as response:
                self.assertIn('Synthetic fixtures',response.read().decode())
            result = request_json(base+'/demo/cooler',{'failed':True},token='session-token')
            self.assertEqual(result['reading']['data']['status'],'failed')
            self.assertEqual(result['candidates']['mode'],'local_directory_fallback')
            self.assertEqual(len(result['candidates']['records']),1)
            turns = request_json(base+'/demo/transport',{},token='session-token')
            self.assertEqual(turns['mode'],'in_process_fallback')
            self.assertFalse(turns['committed'])
            reviews = request_json(base+'/demo/approvals',{},token='session-token')
            self.assertEqual(len(reviews['requests']),2)
            self.assertFalse(reviews['committed'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
