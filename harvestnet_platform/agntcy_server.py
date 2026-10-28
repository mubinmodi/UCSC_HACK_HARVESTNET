"""Native AGNTCY App SDK host. Optional Linux deployment dependency."""
import asyncio
import json
import os
from .systems import organization_systems
from .transport import Receiver, agent_card, load_policy, ORGANIZATIONS
from .transport_auth import AuthError, Verifier, strip_auth


def signed_envelope(body):
    """The DataPart envelope of an A2A message/send body, or ``ValueError``."""
    request = json.loads(body or b'{}')
    parts = request.get('params', {}).get('message', {}).get('parts') if isinstance(request, dict) else None
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict) or not isinstance(parts[0].get('data'), dict):
        raise ValueError('One A2A DataPart envelope required')
    return parts[0]['data']




async def main():
    from a2a.server.agent_execution import AgentExecutor
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import AgentCard, Message, Part, DataPart
    from agntcy_app_sdk.factory import AgntcyFactory

    organization = os.environ['ORGANIZATION_ID']
    if organization not in ORGANIZATIONS:
        raise ValueError('Unknown organization')
    policy, _label = load_policy(os.getenv('AGENT_POLICY'))
    print(f'Policy: {_label}; transport: native AGNTCY A2A, per-sender signed; approvals disabled', flush=True)
    receipts_db = os.getenv('RECEIPTS_DB', ':memory:')
    receiver = Receiver(organization, policy, receipts_db)
    # No shared token: each envelope is checked against its sender's key for this host.
    verifier = Verifier.from_env(organization, receipts_db)
    if os.getenv('AGNTCY_DIRECTORY_ADDRESS'):
        import threading
        from .directory import AgntcyDirectory, DirectoryPublisher
        from .http import seconds
        directory = AgntcyDirectory(os.environ['AGNTCY_DIRECTORY_ADDRESS'])
        publisher = DirectoryPublisher(directory, organization, os.environ['AGENT_PUBLIC_URL'], organization_systems())
        publisher.refresh()  # fail visibly at startup
        # Re-read own systems and republish when capabilities change (cooler failure, new hours).
        interval = seconds(os.getenv('DIRECTORY_REFRESH_SECONDS', '30'))
        threading.Thread(target=publisher.run_forever, args=(interval,), daemon=True).start()

    class Executor(AgentExecutor):
        async def execute(self, context, event_queue):
            parts = context.message.parts
            if len(parts) != 1 or not isinstance(parts[0].root, DataPart):
                raise ValueError('One DataPart envelope required')
            # The signature was checked (and its nonce used) before the SDK saw the request.
            result = receiver.receive(strip_auth(parts[0].root.data))
            import uuid
            await event_queue.enqueue_event(Message(role='agent', message_id=str(uuid.uuid4()), parts=[Part(root=DataPart(data=result))]))

        async def cancel(self, context, event_queue):
            raise ValueError('Transport cannot cancel commitments')

    app = A2AStarletteApplication(
        agent_card=AgentCard.model_validate(agent_card(organization, os.environ['AGENT_PUBLIC_URL'])),
        http_handler=DefaultRequestHandler(agent_executor=Executor(), task_store=InMemoryTaskStore()))

    # Verify the sender's signature before the SDK starts its HTTP host sees the request:
    # read the body, check it, then hand the same bytes on.
    original_build = app.build
    def authenticated_build(*args, **kwargs):
        inner = original_build(*args, **kwargs)
        async def secured(scope, receive, send):
            if scope['type'] != 'http' or scope['method'] == 'GET':
                return await inner(scope, receive, send)
            body, more = b'', True
            while more:
                event = await receive()
                body += event.get('body', b'')
                more = event.get('more_body', False)
                if len(body) > 1_000_000:
                    break
            try:
                if len(body) > 1_000_000:
                    raise AuthError('Message too large')
                verifier.verify(signed_envelope(body))
            except (AuthError, ValueError, AttributeError) as exc:
                raw = json.dumps({'error': f'Authenticated organization message required: {exc}'}).encode()
                await send({'type': 'http.response.start', 'status': 401, 'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': raw})
                return
            delivered = False
            async def replay():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            await inner(scope, replay, send)
        return secured
    app.build = authenticated_build
    factory = AgntcyFactory(enable_tracing=False)
    session = factory.create_app_session(max_sessions=1)
    session.add(app).with_host('0.0.0.0').with_port(int(os.getenv('PORT', '8020'))).with_session_id(organization).build()
    await session.start_all_sessions(keep_alive=True)


if __name__ == '__main__':
    asyncio.run(main())
