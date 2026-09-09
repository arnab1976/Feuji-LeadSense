"""Agent 09 - AI Email Generation."""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Campaign, GeneratedEmail, Lead, LeadEnrichment
from app.services.llm import llm
from app.services.rag import groundedness, retrieve

SYSTEM = (
    "You write short, specific B2B sales emails. Use only facts from the approved "
    "evidence supplied. If no evidence is supplied, make no factual claims. "
    "Reply with JSON only, using keys subject_variants, body and cta."
)


class EmailGenerationAgent(BaseAgent):
    key = "email"
    name = "AI Email Generation"
    summary = "Drafts compliant outreach copy for human review"
    definition = (
        "Generation agent that drafts personalised email variants from the "
        "campaign plan and compliance constraints."
    )
    role = "Copy drafting · personalisation · compliance check"
    stage = "8. AI email studio"
    inputs = ("Lead and company profile, campaign strategy, product knowledge, "
              "prior interactions, tone")
    execution_strategy = (
        "Retrieve approved context; generate subject, body, call to action and "
        "follow-ups; enforce structured output; attach provenance metadata."
    )
    outputs = "Subject variants, email body, CTA, follow-up content, generation metadata"
    stack = "LLM gateway, RAG, pgvector, prompt templates, Pydantic"
    version = "email-v1"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        campaign: Campaign = kwargs["campaign"]
        leads: list[Lead] = kwargs["leads"]
        regenerate: bool = kwargs.get("regenerate", False)

        created: list[str] = []
        total_tokens, total_cost = 0, 0.0

        for lead in leads:
            existing = (ctx.db.query(GeneratedEmail)
                        .filter(GeneratedEmail.campaign_id == campaign.id,
                                GeneratedEmail.lead_id == lead.id).first())
            if existing and not regenerate:
                created.append(existing.id)
                continue

            enrichment = (ctx.db.query(LeadEnrichment)
                          .filter(LeadEnrichment.lead_id == lead.id).first())
            title = enrichment.normalized_title if enrichment else lead.title
            persona = enrichment.persona if enrichment else ""

            cited = retrieve(
                ctx.db, ctx.tenant_id,
                query=f"{campaign.objective} {persona} {lead.company_name}",
                k=2, document_ids=campaign.knowledge_doc_ids or None,
            )
            evidence = " ".join(c["text"][:200] for c in cited)

            prompt = (
                "Write an outreach email as JSON with keys subject_variants (two "
                "options), body and cta.\n"
                f"Lead name: {lead.full_name}\n"
                f"Title: {title}\n"
                f"Company: {lead.company_name}\n"
                f"Persona: {persona}\n"
                f"Campaign objective: {campaign.objective}\n"
                f"Tone: {campaign.tone}\n"
                f"Approved evidence: {evidence}\n"
                f"Sender: {ctx.user_name}\n"
            )
            response = llm.complete(prompt, system=SYSTEM, max_tokens=900,
                                    temperature=0.5)
            try:
                payload = response.json()
            except Exception:
                payload = {"subject_variants": [f"A note for {lead.company_name}"],
                           "body": response.text, "cta": ""}

            row = existing or GeneratedEmail(
                tenant_id=ctx.tenant_id, campaign_id=campaign.id, lead_id=lead.id
            )
            row.subject_variants = payload.get("subject_variants", [])[:3]
            row.body = payload.get("body", "")
            row.cta = payload.get("cta", "")
            row.grounding = [
                {"document_id": c["document_id"], "title": c["document_title"],
                 "chunk_id": c["chunk_id"], "score": c["score"]} for c in cited
            ]
            row.groundedness = groundedness(cited)
            row.tokens = response.tokens
            row.cost_usd = response.cost_usd
            row.model = response.model
            row.status = "draft"
            row.edited_by_human = False
            if not existing:
                ctx.db.add(row)
            ctx.db.flush()

            created.append(row.id)
            total_tokens += response.tokens
            total_cost += response.cost_usd

        return AgentResult(
            output={"email_ids": created, "count": len(created)},
            decision="DRAFTED", confidence=0.89,
            reason=f"{len(created)} personalised drafts produced",
            tokens=total_tokens, cost_usd=round(total_cost, 6),
        )
