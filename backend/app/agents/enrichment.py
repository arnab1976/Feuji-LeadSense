"""Agent 05 - Enrichment.

Runs only on trusted leads (verification cleared). Infers seniority / function /
persona and firmographic signals from extraction + resolved values.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Lead, LeadEnrichment, LeadExtraction, LeadVerification
from app.services.embeddings import cosine, embed
from app.services.taxonomy import (
    function_of, normalize_title, persona_of, seniority, skills_for,
)

DEDUPE_THRESHOLD = 0.93


class EnrichmentAgent(BaseAgent):
    key = "enrichment"
    name = "Enrichment"
    summary = "Adds firmographic, persona and technographic signals"
    definition = (
        "Signal agent that appends seniority, persona, industry and tech-stack "
        "attributes used by ICP scoring."
    )
    description = (
        "Runs only after Verification is clear. It enriches the approved Lead "
        "with market and role context so Scoring can weight fit against the "
        "tenant ICP rubric."
    )
    role = "Firmographics · persona tagging · technographics"
    stage = "4. Enrichment"
    inputs = "Verified lead profile, company context, taxonomy, existing records"
    execution_strategy = (
        "Refuse leads with open verification conflicts; normalise the trusted "
        "title; infer seniority, function and persona; map skills; attach "
        "firmographic / technographic signals; semantic dedupe."
    )
    outputs = "Enriched lead profile, normalised attributes, dedupe links, confidence"
    stack = "LLM structured output, embeddings, pgvector, taxonomy rules, Pydantic"
    version = "enrichment-v1"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        leads: list[Lead] = kwargs["leads"]
        enriched, deduped, skipped = 0, 0, 0
        vectors: list[tuple[str, list[float]]] = []
        items: list[dict] = []

        for lead in leads:
            if self._has_open_conflicts(ctx, lead):
                skipped += 1
                items.append({"lead_id": lead.id, "status": "skipped_open_conflicts"})
                continue

            trusted = self._trusted_values(ctx, lead)
            title = trusted.get("title") or lead.title
            label, rank = seniority(title)
            payload = trusted.get("payload", {})
            vector = embed(f"{title} {trusted.get('company_name', '')}")

            duplicate_of = None
            for other_id, other_vec in vectors:
                if cosine(vector, other_vec) >= DEDUPE_THRESHOLD:
                    duplicate_of = other_id
                    break
            vectors.append((lead.id, vector))
            if duplicate_of:
                lead.duplicate_of_id = duplicate_of
                deduped += 1

            existing = (ctx.db.query(LeadEnrichment)
                        .filter(LeadEnrichment.lead_id == lead.id).first())
            row = existing or LeadEnrichment(tenant_id=ctx.tenant_id, lead_id=lead.id)
            row.normalized_title = normalize_title(title)
            row.seniority = label
            row.seniority_rank = rank
            row.function = function_of(title)
            row.persona = persona_of(title)
            row.skills = skills_for(title)
            row.industry = payload.get("industry", "") or (lead.raw_payload or {}).get("industry", "")
            row.employee_count = int(
                payload.get("employee_count")
                or (lead.raw_payload or {}).get("employee_count") or 0
            )
            row.tech_stack = (payload.get("tech_stack")
                              or (lead.raw_payload or {}).get("tech_stack") or [])
            row.embedding = vector
            row.confidence = 0.94 if title else 0.6
            if not existing:
                ctx.db.add(row)

            # Apply trusted company onto the lead when verification resolved it.
            if trusted.get("company_name"):
                lead.company_name = trusted["company_name"]
            if trusted.get("title"):
                lead.title = trusted["title"]

            lead.status = "enriched"
            enriched += 1
            items.append({
                "lead_id": lead.id,
                "persona": row.persona,
                "seniority": row.seniority,
                "industry": row.industry,
                "tech_stack": row.tech_stack,
                "duplicate_of": duplicate_of,
            })

        ctx.db.flush()
        return AgentResult(
            output={
                "enriched": enriched,
                "deduped": deduped,
                "skipped": skipped,
                "items": items,
                "evidence": {"enriched": enriched, "skipped": skipped},
            },
            decision="ENRICHED" if enriched else "SKIPPED",
            confidence=0.93,
            reason=(
                f"{enriched} leads normalised, {deduped} linked as duplicates, "
                f"{skipped} skipped (open conflicts)"
            ),
        )

    @staticmethod
    def _has_open_conflicts(ctx: AgentContext, lead: Lead) -> bool:
        return (
            ctx.db.query(LeadVerification)
            .filter(
                LeadVerification.lead_id == lead.id,
                LeadVerification.status != "MATCH",
                LeadVerification.resolved_value == "",
            )
            .count()
            > 0
        )

    @staticmethod
    def _trusted_values(ctx: AgentContext, lead: Lead) -> dict:
        """Prefer resolved verification values, then the extraction, then upload."""
        resolved = {
            v.field: (v.resolved_value or v.extracted_value)
            for v in ctx.db.query(LeadVerification)
            .filter(LeadVerification.lead_id == lead.id).all()
            if (v.resolved_value or v.status == "MATCH")
        }
        extraction = (ctx.db.query(LeadExtraction)
                      .filter(LeadExtraction.lead_id == lead.id,
                              LeadExtraction.status == "extracted")
                      .order_by(LeadExtraction.created_at.desc()).first())
        payload = extraction.payload if extraction else {}
        return {
            "title": resolved.get("title") or payload.get("title") or lead.title,
            "company_name": (resolved.get("company_name")
                             or payload.get("company_name") or lead.company_name),
            "payload": payload,
        }
