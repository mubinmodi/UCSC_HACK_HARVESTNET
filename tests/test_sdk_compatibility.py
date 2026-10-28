"""Optional primary SDK validation against the official a2a-sdk and agntcy-dir packages.

These SKIP unless both SDKs are installed (CI's "platform" job installs them). To run them
locally in a throwaway uv environment (this downloads the packages from PyPI once):

    uv run --with pytest --with a2a-sdk==0.3.20 --with agntcy-dir==1.0.0 pytest -q tests/test_sdk_compatibility.py
"""
import asyncio
import threading
import unittest
from http.server import ThreadingHTTPServer
from harvestnet_platform.transport import Receiver, handler_for, agent_card, rpc_request, rpc_result
from harvestnet_platform.directory import record_for
from harvestnet_platform.systems import Systems
from test_transport import envelope, signer, verifier

MISSING = None
try:
    import httpx
    from a2a.types import AgentCard, Message, SendMessageRequest, SendMessageResponse
    from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
    from agntcy.dir_sdk.models import core_v1
    from google.protobuf.json_format import ParseDict
    AVAILABLE = True
except ImportError as exc:
    AVAILABLE, MISSING = False, exc.name


@unittest.skipUnless(AVAILABLE, f'SKIPPED SDK CHECK: optional a2a-sdk/agntcy-dir not installed (missing {MISSING}); '
                                'run: uv run --with pytest --with a2a-sdk==0.3.20 --with agntcy-dir==1.0.0 pytest -q tests/test_sdk_compatibility.py')
class SDKCompatibilityTests(unittest.TestCase):
    def test_official_sdk_accepts_cards_messages_and_directory_records(self):
        AgentCard.model_validate(agent_card('city','http://localhost:8020'))
        SendMessageRequest.model_validate(rpc_request(signer().sign(envelope(), 'market')))
        SendMessageResponse.model_validate(rpc_result({'id':'test'},{}))
        proto = core_v1.Record()
        ParseDict(record_for('city','http://localhost:8020',Systems()),proto.data)

    def test_official_a2a_client_calls_our_http_server(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),handler_for(Receiver('market'),verifier('market'),'http://localhost'))
        base = f'http://127.0.0.1:{server.server_port}'
        # Replace the startup card URL with the actual dynamically bound port.
        server.RequestHandlerClass = handler_for(Receiver('market'),verifier('market'),base)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        async def exchange():
            async with httpx.AsyncClient() as http:
                card = await A2ACardResolver(httpx_client=http,base_url=base).get_agent_card()
                client = ClientFactory(ClientConfig(httpx_client=http,streaming=False)).create(card)
                message = Message.model_validate(rpc_request(signer().sign(envelope(), 'market'))['params']['message'])
                events = [event async for event in client.send_message(message)]
                self.assertEqual(len(events),1)
                self.assertEqual(events[0].parts[0].root.data['move']['action'],'ask_human')
        try:
            asyncio.run(exchange())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
