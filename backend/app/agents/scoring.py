"""Agent 06 - ICP & Lead Scoring.

Scores enriched leads only. Prefer LeadEnrichment signals; fall back carefully
when a lead was enriched in an earlier step of the same workflow.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Lead, LeadEnrichment, LeadScore
from app.services.policy import get_policy
from app.services.scoring import DEFAULT_WEIGHTS, score_lead


class ScoringAgent(BaseAgent):
    key = "scoring"
    name = "ICP & Lead Scoring"
    summary = "Scores ICP fit and produces evidence bands"
    definition = (
        "Scoring agent that weights enriched signals against the tenant Ideal "
        "Customer Profile and emits band + factor evidence."
    )
    description = (
        "Applies the ICP rubric to enriched leads, explains factor contributions, "
        "and stores score bands for analytics and downstream campaign planning."
    )
    role = "ICP fit · weighted scoring · band assignment"
    stage = "5. ICP scoring"
    inputs = "Enriched lead, ICP rules, historical engagement and conversion features"
    execution_strategy = (
        "Require an enrichment row (or status=enriched); calculate a weighted "
        "rule score; explain each factor; band HOT / HIGH / MEDIUM / LOW."
    )
    outputs = "0-100 score, HOT / HIGH / MEDIUM / LOW class, score factors"
    stack = "Python rules; optional XGBoost, LightGBM or logistic regression later"
    version = "scoring-v1"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        leads: list[Lead] = kwargs["leads"]
        weights = kwargs.get("weights") or get_policy(
            ctx.db, ctx.tenant_id
        ).scoring_weights or DEFAULT_WEIGHTS
        engagement_map = kwargs.get("engagement") or {}

        bands: dict[str, int] = {}
        items: list[dict] = []
        skipped = 0

        for lead in leads:
            enrichment = (ctx.db.query(LeadEnrichment)
                          .filter(LeadEnrichment.lead_id == lead.id).first())
            if not enrichment and lead.status not in ("enriched", "scored"):
                skipped += 1
                items.append({"lead_id": lead.id, "status": "skipped_not_enriched"})
                continue

            raw = lead.raw_payload or {}
            result = score_lead(
                title=(enrichment.normalized_title if enrichment else lead.title),
                industry=(enrichment.industry if enrichment else raw.get("industry", "")),
                employee_count=(enrichment.employee_count if enrichment
                                else int(raw.get("employee_count") or 0)),
                tech_stack=(enrichment.tech_stack if enrichment
                            else raw.get("tech_stack", [])),
                engagement=engagement_map.get(lead.id, {}),
                weights=weights,
            )
            ctx.db.query(LeadScore).filter(LeadScore.lead_id == lead.id).delete()
            ctx.db.add(LeadScore(
                tenant_id=ctx.tenant_id, lead_id=lead.id, score=result["score"],
                band=result["band"], factors=result["factors"], weights=weights,
            ))
            lead.status = "scored"
            bands[result["band"]] = bands.get(result["band"], 0) + 1
            items.append({
                "lead_id": lead.id,
                "score": result["score"],
                "band": result["band"],
                "factors": result["factors"],
            })

        ctx.db.flush()
        return AgentResult(
            output={
                "bands": bands,
                "items": items,
                "weights": weights,
                "skipped": skipped,
                "evidence": {"bands": bands, "skipped": skipped},
            },
            decision="SCORED" if items and any("score" in i for i in items) else "SKIPPED",
            confidence=0.88,
            reason=(
                ", ".join(f"{count} {band}" for band, count in bands.items())
                or f"no leads scored ({skipped} skipped)"
            ),
        )
