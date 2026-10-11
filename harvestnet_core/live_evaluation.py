"""Explicit real-agent evaluation adapter, shared cap and durable result publication."""
from harvestnet_agents.llm_negotiators import LLMNegotiator,SpendingCap
from harvestnet_agents.negotiation import parse_agent_input
from .calculators import Calculators
from .evaluation import evaluate
from .protocol import number


class LLMProvider:
    label='LLM negotiators with real core calculators; fallback sources recorded'
    def __init__(self,client,*,limit_usd=0,allow_paid=False,config=None):
        limit_usd=number(limit_usd)
        if limit_usd>100:
            raise ValueError('cap must be between zero and 100 USD')
        if limit_usd>0 and not allow_paid:
            raise ValueError('paid calls require explicit authorization')
        self.client=client
        self.cap=SpendingCap(limit_usd)
        self.config=config
        self.decisions=[]
        self.metadata=None
        self.agents={}

    def __call__(self,org,wire):
        role,typed=parse_agent_input({**wire,'turn':wire['turn_context']})
        key=(wire['policy_session'],role,org)
        if key not in self.agents:
            self.agents[key]=LLMNegotiator(role,org,cap=self.cap,client=self.client,config=self.config,calculators=Calculators())
        agent=self.agents[key]
        decision=agent.decide(typed)
        self.decisions.append(decision)
        self.metadata={'source':decision.source,'model_calls':decision.model_calls,'number_check_failures':decision.number_check_failures,'cost_usd':decision.cost_usd,'fallback_reason':decision.fallback_reason}
        return decision.move.to_dict()

    def pop_metadata(self):
        metadata=self.metadata
        self.metadata=None
        return metadata


def publish_evaluation(fixture,records,*,llm_provider=None,repeats=1,output=None):
    result=evaluate(fixture,llm_provider=llm_provider,repeats=repeats,output=output)
    if llm_provider:
        result['llm_cost_usd']=llm_provider.cap.spent_usd
        result['llm_cap_usd']=llm_provider.cap.limit_usd
    with records.transaction(): records.put('results',fixture['scenario_id'],result)
    return result
