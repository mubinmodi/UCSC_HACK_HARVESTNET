"""Join seam for Lane A's harness and Lane B's real deterministic policies.

No real-agent module is invented here. Missing dependencies fail explicitly.
"""
import argparse
import copy
import importlib
import json
import os
import threading
import uuid
from pathlib import Path
from .transport import ORGANIZATIONS, Receiver, InProcess, A2ATransport, canonical, load_policy, validate_move

REQUIRED_CHECKS = {'no_double_booking', 'pounds_conserved', 'versioned_approvals',
                   'no_auto_commit', 'all_pounds_have_pathway', 'zero_invalid_commitments'}


class MoveBridge:
    def __init__(self, transport, event_id=None):
        self.transport, self.event = transport, event_id or str(uuid.uuid4())
        self.sequence, self.pending = 0, None
        self.lock = threading.RLock()

    def __call__(self, organization, agent_input):
        if not isinstance(agent_input, dict) or organization not in ORGANIZATIONS or agent_input.get('turn') != organization:
            raise ValueError('Harness must follow the published organization turn')
        with self.lock:
            envelope = {'event_id': self.event, 'sequence':self.sequence+1,
                        'turn':organization,'input':copy.deepcopy(agent_input)}
            if self.pending and canonical(envelope) != canonical(self.pending):
                raise ValueError('A partial delivery must retry the identical turn before advancing')
            self.pending = envelope
            receipts = self.transport.broadcast(envelope)
            moves = [r['move'] for r in receipts if r['organization_id'] == organization]
            if len(moves) != 1 or moves[0] is None:
                raise ValueError('One move from its own organization required')
            move = validate_move(moves[0], organization, agent_input['draft']['version'])
            self.sequence += 1
            self.pending = None
            return move


def require_outcomes(run):
    if not isinstance(run,dict) or any(key not in run for key in ('commitments','pathways','rule_checks')):
        raise ValueError('Harness must return commitments, pathways and all required rule checks')
    checks = run['rule_checks']
    if not isinstance(checks,dict) or REQUIRED_CHECKS-set(checks) or any(value is not True for value in checks.values()):
        raise ValueError('Networked/core rule checks are absent or failed')
    if not isinstance(run['commitments'],list) or not isinstance(run['pathways'],list):
        raise ValueError('Commitments and pathways must be lists')
    return {key:run[key] for key in ('commitments','pathways','rule_checks')}


def compare_fixture(fixture, harness, policy, network):
    local = InProcess({org:Receiver(org,policy) for org in ORGANIZATIONS})
    # Same fixture/clock/policy/facts, fresh event namespaces, zero live LLM calls.
    baseline = harness(copy.deepcopy(fixture),MoveBridge(local))
    remote = harness(copy.deepcopy(fixture),MoveBridge(network))
    expected, observed = require_outcomes(baseline), require_outcomes(remote)
    if canonical(expected) != canonical(observed):
        raise ValueError('Networked commitments/pathways differ from in-process outcomes')
    return {'status':'identical_outcomes','in_process_mode':local.mode,'network_mode':network.mode,
            'commitments':observed['commitments'],'pathways':observed['pathways'],
            'rule_checks':observed['rule_checks']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture',required=True)
    parser.add_argument('--harness',required=True,help='Lane A module:function accepting (fixture,move_provider)')
    parser.add_argument('--policy',required=True,help='Lane B module:function accepting (organization,input)')
    parser.add_argument('--output',default='output/join-report.json')
    args = parser.parse_args()
    try:
        harness, _ = load_policy(args.harness)
        policy, label = load_policy(args.policy)
    except (ImportError,AttributeError) as exc:
        parser.error(f'Real harness/negotiators not available: {exc}')
    if policy.__module__ == 'harvestnet_platform.transport':
        parser.error('A stand-in is not evidence for the real-agent join')
    endpoints = json.loads(os.environ['AGENT_ENDPOINTS'])
    network = A2ATransport(endpoints,os.environ['TRANSPORT_TOKEN'])
    report = compare_fixture(json.loads(Path(args.fixture).read_text()),harness,policy,network)
    report['policy'] = args.policy
    report['harness'] = args.harness
    # The caller must ensure peers use the same adapter/image; documented below.
    report['fixture'] = args.fixture
    output = Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(f'Join checked; report written to {output}')


if __name__ == '__main__':
    main()
