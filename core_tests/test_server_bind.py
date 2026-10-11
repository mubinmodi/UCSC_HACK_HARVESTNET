"""The core server binds 127.0.0.1 unless HOST says otherwise (a container sets HOST=0.0.0.0)."""
import unittest
from pathlib import Path
from harvestnet_core.server import bind_address, make_server


class _NoAPI:
    def call(self, *args):
        return 200, {}


class BindAddressTests(unittest.TestCase):
    def test_defaults_to_localhost_and_8050(self):
        self.assertEqual(bind_address({}), ('127.0.0.1', 8050))

    def test_host_and_port_come_from_the_environment(self):
        self.assertEqual(bind_address({'HOST': '0.0.0.0', 'PORT': '8000'}), ('0.0.0.0', 8000))

    def test_server_binds_the_requested_host(self):
        server = make_server(_NoAPI(), host='127.0.0.1', port=0)
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
        finally:
            server.server_close()

    def test_main_passes_host_to_the_server(self):
        # The entry point must use bind_address() for both host and port.
        source = (Path(__file__).parents[1] / 'harvestnet_core' / 'server.py').read_text()
        main = source.split("if __name__=='__main__':", 1)[1]
        self.assertIn('bind_address()', main)
        self.assertIn('host=host', main)

    def test_invalid_port_is_rejected(self):
        with self.assertRaises(ValueError):
            bind_address({'PORT': 'eighty'})


if __name__ == '__main__':
    unittest.main()
