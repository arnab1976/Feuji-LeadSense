"""The 13 agent responsibilities.

They are 13 classes, not 13 microservices. For the demonstration they all run
inside one orchestration process with deterministic services around them; the
production decomposition in docs/architecture.md groups them into ten services.
"""
from app.agents.base import AgentContext, AgentResult, BaseAgent  # noqa: F401
from app.agents.compliance import ComplianceAgent
from app.agents.email_generation import EmailGenerationAgent
from app.agents.engagement import EngagementIntelligenceAgent
from app.agents.enrichment import EnrichmentAgent
from app.agents.execution import CampaignExecutionAgent
from app.agents.extraction import ExtractionAgent
from app.agents.ingestion import LeadIngestionAgent
from app.agents.reply_nba import ReplyIntelligenceAgent
from app.agents.scoring import ScoringAgent
from app.agents.segmentation import SegmentationAgent
from app.agents.strategy import CampaignStrategyAgent
from app.agents.supervisor import SupervisorAgent
from app.agents.verification import VerificationAgent

#: Ordered catalog. The order is the reference execution order, which is also the
#: order the portal's workflow spine renders.
AGENT_CLASSES: list[type[BaseAgent]] = [
    SupervisorAgent, LeadIngestionAgent, ExtractionAgent, VerificationAgent,
    EnrichmentAgent, ScoringAgent, SegmentationAgent, CampaignStrategyAgent,
    EmailGenerationAgent, ComplianceAgent, CampaignExecutionAgent,
    EngagementIntelligenceAgent, ReplyIntelligenceAgent,
]

AGENTS: dict[str, BaseAgent] = {cls.key: cls() for cls in AGENT_CLASSES}


def get_agent(key: str) -> BaseAgent:
    if key not in AGENTS:
        raise KeyError(f"Unknown agent '{key}'")
    return AGENTS[key]


def catalog() -> list[dict]:
    return [
        {"number": idx + 1, **cls.describe()}
        for idx, cls in enumerate(AGENT_CLASSES)
    ]


__all__ = ["AGENTS", "AGENT_CLASSES", "AgentContext", "AgentResult", "BaseAgent",
           "catalog", "get_agent"]
