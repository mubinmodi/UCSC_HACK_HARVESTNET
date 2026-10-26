"""Core/transport identity boundary; the exact same real policy in both modes."""
from functools import lru_cache
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from .calculators import Calculators
from .engine import run_fixture


@lru_cache(maxsize=256)
def owner_policy(session,role,organization):
    return rules_negotiator(role,organization,Calculators())


def policy(organization,data):
    context=data['turn_context']
    # The transport's IDs are organization IDs (contract decision 1): the donor is the lot's donor.
    donor=organization==data['draft']['donor_id']
    if data.get('turn')!=organization or context['organization_id']!=organization:
        raise ValueError('transport identity does not match core turn')
    role='donor' if donor else 'advocate' if organization=='advocate' else 'food_bank'
    role,typed=parse_agent_input({'role':role,'draft':data['draft'],'facts':data['facts'],'turn':context})
    session=data['policy_session']
    if not isinstance(session,str) or not session:
        raise ValueError('core policy session is required')
    move=owner_policy(session,role,organization).move(typed).to_dict()
    move['organization_id']=organization
    if 'resource_owner' in move: move['resource_owner']=organization
    return move


def harness(fixture,move_provider):
    donors={o['organization_id'] for o in fixture['organizations'] if o['role']=='donor'}
    if len(donors)!=1: raise ValueError('MVP transport requires one donor')
    def adapter(org,data):
        wire_org=org  # contract decision 1: the transport uses organization IDs
        move=move_provider(wire_org,{**data,'turn':wire_org})
        if move['organization_id']!=wire_org: raise ValueError('transport returned a different owner')
        move={**move,'organization_id':org}
        if 'resource_owner' in move: move['resource_owner']=org
        return move
    return run_fixture(fixture,adapter)
