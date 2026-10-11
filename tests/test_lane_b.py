"""Run published Lane B rules over HTTP; these remain recorded calculator tests."""
import copy
import importlib.util
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from harvestnet_platform.lane_b import recorded_rules, real_rules
from harvestnet_platform.transport import ORGANIZATIONS, Receiver, A2ATransport, handler_for, validate_move


@unittest.skipUnless(importlib.util.find_spec('harvestnet_agents') and os.getenv('LANE_B_FIXTURES'),
                     'Install pinned Lane B package and set LANE_B_FIXTURES to run compatibility tests')
class LaneBTests(unittest.TestCase):
    def test_all_recorded_moves_match_direct_rules_over_five_http_hosts(self):
        from harvestnet_agents.negotiation import parse_agent_input
        from harvestnet_agents.rules_negotiators import rules_negotiator
        servers, threads, endpoints = [], [], {}
        try:
            for org in ORGANIZATIONS:
                server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Receiver(org, recorded_rules), 'lane-b-test', 'http://localhost'))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                servers.append(server)
                threads.append(thread)
                endpoints[org] = f'http://127.0.0.1:{server.server_port}'
            fixtures = sorted(Path(os.environ['LANE_B_FIXTURES']).glob('*.json'))
            self.assertGreaterEqual(len(fixtures), 25)
            network = A2ATransport(endpoints, 'lane-b-test')
            for file in fixtures:
                raw = json.loads(file.read_text())
                role, typed = parse_agent_input(raw)
                actor = raw['turn']['organization_id']  # organization IDs are the same on the wire
                expected = rules_negotiator(role, actor).move(typed).to_dict()
                self.assertEqual(expected['action'], raw['expected']['kind'])
                # Lane B's AgentInput travels unchanged inside the envelope.
                data = {key: raw[key] for key in ('role', 'draft', 'facts', 'turn')}
                envelope = {'event_id': file.stem, 'sequence': 1, 'turn': actor, 'input': data}
                with self.subTest(fixture=file.stem):
                    receipts = network.broadcast(envelope)
                    self.assertEqual(next(r['move'] for r in receipts if r['organization_id'] == actor), expected)
                    self.assertEqual(network.broadcast(envelope), receipts)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()

    def test_real_adapter_requires_core_calculators_and_explicit_matching_turn(self):
        raw = json.loads((Path(os.environ['LANE_B_FIXTURES']) / 'donor_accepts_plan_before_deadline.json').read_text())
        data = {key: raw[key] for key in ('role', 'draft', 'facts', 'turn')}
        self.assertEqual(recorded_rules('market', data)['action'], 'accept')
        # Lane A's earlier wire form gives the same move.
        legacy = {'turn': 'market', 'turn_context': raw['turn'], 'draft': raw['draft'], 'facts': raw['facts']}
        self.assertEqual(recorded_rules('market', legacy), recorded_rules('market', data))
        with patch.dict(os.environ, {'LANE_B_CALCULATORS': ''}):
            with self.assertRaises(ValueError):
                real_rules('market', data)
        missing = copy.deepcopy(legacy)
        del missing['turn_context']
        for bad in (missing, {**data, 'role': 'food_bank'}, {**data, 'turn': {**raw['turn'], 'number': 0}}):
            with self.assertRaises(ValueError):
                recorded_rules('market', bad)


class AdvocateTransportTests(unittest.TestCase):
    def test_advocate_can_pass_but_cannot_ask_human_to_commit(self):
        move = {'organization_id': 'advocate', 'version': 1, 'action': 'pass', 'reason': 'No amendment to propose'}
        self.assertEqual(validate_move(move, 'advocate', 1), move)
        with self.assertRaises(ValueError):
            validate_move({**move, 'action': 'ask_human'}, 'advocate', 1)
