"""Adapter to Lane B's typed rules, without replacing its policies or calculators.

`recorded_rules` uses Lane B's explicitly labeled stand-in calculators for interface
verification only. `real_rules` requires the reviewed Lane A calculator factory.
"""
import copy
import importlib
import json
import os
from .transport import ORGANIZATIONS, validate_move


def _move(organization, data, *, recorded=False):
    from harvestnet_agents.negotiation import parse_agent_input
    from harvestnet_agents.rules_negotiators import rules_negotiator
    from harvestnet_agents.calculators import StandInCalculators

    if organization not in ORGANIZATIONS or data.get('turn') != organization:
        raise ValueError('Lane B adapter requires its published organization turn')
    # Domain IDs may differ from transport IDs (the recorded donor is "market").
    ids = {org: org for org in ORGANIZATIONS}
    configured = json.loads(os.getenv('LANE_B_ORGANIZATION_IDS', '{}'))
    if not isinstance(configured, dict) or set(configured) - set(ids):
        raise ValueError('Invalid Lane B organization ID mapping')
    ids.update(configured)
    if any(not isinstance(value, str) or not value for value in ids.values()) or len(set(ids.values())) != len(ids):
        raise ValueError('Lane B organization IDs must be distinct nonempty strings')
    # Bank IDs appear in amendments; preserve them rather than rewriting plans.
    if any(ids[org] != org for org in ('city', 'rural', 'eastside', 'advocate')):
        raise ValueError('Only donor ID aliasing is supported; agree other IDs with the core')
    context = data.get('turn_context')
    if not isinstance(context, dict) or context.get('organization_id') != ids[organization]:
        raise ValueError('Explicit Lane B turn context with matching identity is required')
    if type(context.get('number')) is not int or context['number'] < 1 or not context.get('now'):
        raise ValueError('Core-provided turn number and clock are required; neither is invented')
    role = 'donor' if organization == 'donor' else 'advocate' if organization == 'advocate' else 'food_bank'
    role, typed_input = parse_agent_input(copy.deepcopy({
        'role': role, 'draft': data['draft'], 'facts': data['facts'], 'turn': context}))
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
    move = rules_negotiator(role, ids[organization], calculators).move(typed_input).to_dict()
    if move['organization_id'] != ids[organization]:
        raise ValueError('Lane B move names a different organization')
    move['organization_id'] = organization
    if 'resource_owner' in move:
        if move['resource_owner'] != ids[organization]:
            raise ValueError('Lane B hold names a different resource owner')
        move['resource_owner'] = organization
    return validate_move(move, organization, data['draft']['version'])


def recorded_rules(organization, data):
    return _move(organization, data, recorded=True)


recorded_rules.uses_stand_in_calculators = True


def real_rules(organization, data):
    return _move(organization, data)
