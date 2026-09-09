"""Agent 08 - Campaign Strategy."""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Campaign, Lead, LeadEnrichment, SegmentMember
from app.services.llm import llm
from app.services.rag import groundedness, retrieve

SYSTEM = (
    "You are a B2B campaign strategist. Ground every claim in the supplied "
    "approved knowledge. Never invent statistics. Reply with JSON only."
)


class CampaignStrategyAgent(BaseAgent):
    key = "strategy"
    name = "Campaign Strategy"
    role = "Converts a sales objective into a campaign plan"
    inputs = "Product or offering, target market, segment, sales objective, approved knowledge"
    execution_strategy = (
        "Retrieve relevant product knowledge; identify the audience, pain and "
        "value proposition; propose the sequence, tone, call to action and schedule."
    )
    outputs = "Campaign brief, target roles, sequence plan, messaging themes"
    stack = "LangGraph, LLM, RAG, pgvector, product knowledge base"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        campaign: Campaign = kwargs["campaign"]

        members = (ctx.db.query(Lead, LeadEnrichment)
                   .join(SegmentMember, SegmentMember.lead_id == Lead.id)
                   .outerjoin(LeadEnrichment, LeadEnrichment.lead_id == Lead.id)
                   .filter(SegmentMember.segment_id == campaign.segment_id).all())
        personas = sorted({(e.persona if e else "") or "General business"
                           for _, e in members})
        industries = sorted({(e.industry if e else "") for _, e in members if e and e.industry})

        cited = retrieve(
            ctx.db, ctx.tenant_id,
            query=f"{campaign.objective} {' '.join(personas)} {' '.join(industries)}",
            k=4, document_ids=campaign.knowledge_doc_ids or None,
        )
        evidence = "\n".join(f"- [{c['document_title']}] {c['text'][:240]}" for c in cited)

        prompt = (
            "Produce a campaign_brief as JSON with keys: audience, pain, "
            "value_proposition, messaging_themes (list), sequence (list of "
            "{day, step, goal}).\n"
            f"Segment: {', '.join(personas) or 'mixed'}\n"
            f"Industries: {', '.join(industries) or 'mixed'}\n"
            f"Audience size: {len(members)}\n"
            f"Objective: {campaign.objective}\n"
            f"Tone: {campaign.tone}\n"
            f"Approved knowledge:\n{evidence or '- none enabled'}\n"
        )
        response = llm.complete(prompt, system=SYSTEM, max_tokens=1200)
        try:
            brief = response.json()
        except Exception:
            brief = {"audience": ", ".join(personas), "pain": "", "value_proposition": "",
                     "messaging_themes": [], "sequence": []}

        brief["cited_documents"] = [
            {"document_id": c["document_id"], "title": c["document_title"],
             "score": c["score"]} for c in cited
        ]
        brief["groundedness"] = groundedness(cited)
        brief["target_personas"] = personas
        brief["audience_size"] = len(members)

        campaign.strategy = brief
        campaign.status = "planned"
        ctx.db.flush()

        return AgentResult(
            output={"strategy": brief},
            decision="PLAN_READY", confidence=brief["groundedness"] or 0.6,
            reason=(f"Plan grounded in {len(cited)} approved sources for "
                    f"{len(members)} leads"),
            tokens=response.tokens, cost_usd=response.cost_usd, model=response.model,
        )
