"""Native AGNTCY App SDK host. Optional Linux deployment dependency."""
import asyncio
import json
import os
from .transport import Receiver, agent_card, load_policy, ORGANIZATIONS


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
    token = os.environ['TRANSPORT_TOKEN']
    if not token:
        raise ValueError('Transport token required')
    policy, _label = load_policy(os.getenv('AGENT_POLICY'))
    print(f'Policy: {_label}; transport: native AGNTCY A2A; approvals disabled', flush=True)
    receiver = Receiver(organization, policy, os.getenv('RECEIPTS_DB', ':memory:'))
    if os.getenv('AGNTCY_DIRECTORY_ADDRESS'):
        from .directory import AgntcyDirectory, record_for
        from .systems import Systems
        directory = AgntcyDirectory(os.environ['AGNTCY_DIRECTORY_ADDRESS'])
        record = record_for(organization, os.environ['AGENT_PUBLIC_URL'], Systems(os.getenv('BEECEPTOR_BASE_URL')))
        directory.register(record)

    class Executor(AgentExecutor):
        async def execute(self, context, event_queue):
            parts = context.message.parts
            if len(parts) != 1 or not isinstance(parts[0].root, DataPart):
                raise ValueError('One DataPart envelope required')
            result = receiver.receive(parts[0].root.data)
            import uuid
            await event_queue.enqueue_event(Message(role='agent', message_id=str(uuid.uuid4()), parts=[Part(root=DataPart(data=result))]))

        async def cancel(self, context, event_queue):
            raise ValueError('Transport cannot cancel commitments')

    app = A2AStarletteApplication(
        agent_card=AgentCard.model_validate(agent_card(organization, os.environ['AGENT_PUBLIC_URL'])),
        http_handler=DefaultRequestHandler(agent_executor=Executor(), task_store=InMemoryTaskStore()))

    # Authenticate the ASGI application before the SDK starts its HTTP host.
    original_build = app.build
    def authenticated_build(*args, **kwargs):
        inner = original_build(*args, **kwargs)
        async def secured(scope, receive, send):
            import hmac
            if scope['type'] == 'http' and scope['method'] != 'GET':
                headers = dict(scope['headers'])
                if not hmac.compare_digest(headers.get(b'authorization', b''), f'Bearer {token}'.encode()):
                    await send({'type': 'http.response.start', 'status': 401, 'headers': [(b'content-type', b'application/json')]})
                    await send({'type': 'http.response.body', 'body': b'{"error":"Unauthorized"}'})
                    return
            await inner(scope, receive, send)
        return secured
    app.build = authenticated_build
    factory = AgntcyFactory(enable_tracing=False)
    session = factory.create_app_session(max_sessions=1)
    session.add(app).with_host('0.0.0.0').with_port(int(os.getenv('PORT', '8020'))).with_session_id(organization).build()
    await session.start_all_sessions(keep_alive=True)


if __name__ == '__main__':
    asyncio.run(main())
