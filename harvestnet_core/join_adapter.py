"""Core/transport identity boundary; the exact same real policy in both modes."""
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from .calculators import Calculators
from .engine import run_fixture


def policy(organization,data):
    context=data['turn_context']
    domain_org=data['draft']['donor_id'] if organization=='donor' else organization
    if data.get('turn')!=organization or context['organization_id']!=domain_org:
        raise ValueError('transport identity does not match core turn')
    role='donor' if organization=='donor' else 'advocate' if organization=='advocate' else 'food_bank'
    role,typed=parse_agent_input({'role':role,'draft':data['draft'],'facts':data['facts'],'turn':context})
    move=rules_negotiator(role,domain_org,Calculators()).move(typed).to_dict()
    move['organization_id']=organization
    if 'resource_owner' in move: move['resource_owner']=organization
    return move


def harness(fixture,move_provider):
    donors={o['organization_id'] for o in fixture['organizations'] if o['role']=='donor'}
    if len(donors)!=1: raise ValueError('MVP transport requires one donor')
    def adapter(org,data):
        wire_org='donor' if org in donors else org
        move=move_provider(wire_org,{**data,'turn':wire_org})
        if move['organization_id']!=wire_org: raise ValueError('transport returned a different owner')
        move={**move,'organization_id':org}
        if 'resource_owner' in move: move['resource_owner']=org
        return move
    return run_fixture(fixture,adapter)
