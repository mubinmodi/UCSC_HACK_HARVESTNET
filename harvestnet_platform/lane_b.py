"""Adapter to Lane B's typed rules, without replacing its policies or calculators.

The transport carries Lane B's ``AgentInput`` unchanged: ``{role, draft, facts, turn}``
(docs/contracts/README.md decision 5). Organization IDs are the same on the wire and in
Lane B (decision 1), so nothing is renamed. Lane A's earlier wire form (``turn`` as the
organization ID plus ``turn_context``) is still read.

`recorded_rules` uses Lane B's explicitly labeled stand-in calculators for interface
verification only. `real_rules` requires the reviewed Lane A calculator factory.
"""
import copy
import importlib
import os
from .transport import ORGANIZATIONS, role_of, turn_organization, validate_move


def lane_b_input(organization, data):
    """Lane B's AgentInput for this organization's turn, from either wire form."""
    if organization not in ORGANIZATIONS or turn_organization(data) != organization:
        raise ValueError('Lane B adapter requires its published organization turn')
    turn = data['turn'] if isinstance(data.get('turn'), dict) else data.get('turn_context')
    if not isinstance(turn, dict) or turn.get('organization_id') != organization:
        raise ValueError('Explicit Lane B turn with matching identity is required')
    if type(turn.get('number')) is not int or turn['number'] < 1 or not turn.get('now'):
        raise ValueError('Core-provided turn number and clock are required; neither is invented')
    role = data.get('role', role_of(organization))
    if role != role_of(organization):
        raise ValueError('Agent input role does not match the organization')
    return {'role': role, 'draft': data['draft'], 'facts': data['facts'], 'turn': turn}


def _move(organization, data, *, recorded=False):
    from harvestnet_agents.negotiation import parse_agent_input
    from harvestnet_agents.rules_negotiators import rules_negotiator
    from harvestnet_agents.calculators import StandInCalculators

    role, typed_input = parse_agent_input(copy.deepcopy(lane_b_input(organization, data)))
    if recorded:
        calculators = StandInCalculators()
    else:
        spec = os.getenv('LANE_B_CALCULATORS', '')
        module, separator, name = spec.partition(':')
        if not separator:
            raise ValueError('Real rules require LANE_B_CALCULATORS=module:factory from Lane A')
        calculators = getattr(importlib.import_module(module), name)()
        if isinstance(calculators, StandInCalculators):
            raise ValueError('Stand-in calculators cannot certify the real-agent join')
    move = rules_negotiator(role, organization, calculators).move(typed_input).to_dict()
    return validate_move(move, organization, data['draft']['version'])


def recorded_rules(organization, data):
    return _move(organization, data, recorded=True)


recorded_rules.uses_stand_in_calculators = True


def real_rules(organization, data):
    return _move(organization, data)
