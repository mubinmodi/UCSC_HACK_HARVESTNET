"""Core/transport identity boundary; the exact same real policy in both modes."""
from functools import lru_cache
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from .calculators import Calculators
from .engine import run_fixture


@lru_cache(maxsize=256)
def owner_policy(session,role,organization):
    return rules_negotiator(role,organization,Calculators())


def _turn(organization,data):
    """The typed turn from the core's wire form, and the core's policy session."""
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
    return role,typed,session


def _own(organization,move):
    move['organization_id']=organization
    if 'resource_owner' in move: move['resource_owner']=organization
    return move


def policy(organization,data):
    role,typed,session=_turn(organization,data)
    return _own(organization,owner_policy(session,role,organization).move(typed).to_dict())


class LLMPolicy:
    """An organization host's own Claude negotiator (``AGENT_POLICY=harvestnet_core.join_adapter:llm_policy``),
    under that host's own spending cap: ``CLAUDE_RUN_CAP_USD`` and ``CLAUDE_TOTAL_CAP_USD`` against the
    spend ledger at ``CLAUDE_SPEND_LEDGER`` (``SpendingCap.from_env``). With no cap (the default, 0) it
    makes no model call and answers with its rules move, labeled ``fallback``. ``pop_metadata`` reports
    each move's source, calls and cost; the host returns that with the move."""
    def __init__(self,client=None,cap=None):
        self.client,self.cap=client,cap
        self.agents={}
        self.metadata=None

    def __call__(self,organization,data):
        from harvestnet_agents.llm_negotiators import LLMNegotiator,SpendingCap
        role,typed,session=_turn(organization,data)
        if self.cap is None:
            self.cap=SpendingCap.from_env(caller=f'host:{organization}')
        key=(session,role,organization)
        if key not in self.agents:
            if len(self.agents)>=256: self.agents.clear()
            self.agents[key]=LLMNegotiator(role,organization,cap=self.cap,client=self.client,calculators=Calculators())
        decision=self.agents[key].decide(typed)
        self.metadata={'source':decision.source,'model_calls':decision.model_calls,'number_check_failures':decision.number_check_failures,
                       'cost_usd':decision.cost_usd,'fallback_reason':decision.fallback_reason}
        return _own(organization,decision.move.to_dict())

    def pop_metadata(self):
        metadata,self.metadata=self.metadata,None
        return metadata


llm_policy=LLMPolicy()


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
