"""Agent 06 - ICP & Lead Scoring."""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Lead, LeadEnrichment, LeadScore
from app.services.policy import get_policy
from app.services.scoring import DEFAULT_WEIGHTS, score_lead


class ScoringAgent(BaseAgent):
    key = "scoring"
    name = "ICP & Lead Scoring"
    role = "Calculates sales relevance and priority"
    inputs = "Enriched lead, ICP rules, historical engagement and conversion features"
    execution_strategy = (
        "Calculate a weighted rule score for the MVP; explain each factor's "
        "contribution; move to supervised ranking later where data supports it."
    )
    outputs = "0-100 score, HOT / HIGH / MEDIUM / LOW class, score factors"
    stack = "Python rules; optional XGBoost, LightGBM or logistic regression later"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        leads: list[Lead] = kwargs["leads"]
        weights = kwargs.get("weights") or get_policy(
            ctx.db, ctx.tenant_id
        ).scoring_weights or DEFAULT_WEIGHTS

        bands: dict[str, int] = {}
        items: list[dict] = []

        for lead in leads:
            enrichment = (ctx.db.query(LeadEnrichment)
                          .filter(LeadEnrichment.lead_id == lead.id).first())
            raw = lead.raw_payload or {}
            result = score_lead(
                title=(enrichment.normalized_title if enrichment else lead.title),
                industry=(enrichment.industry if enrichment else raw.get("industry", "")),
                employee_count=(enrichment.employee_count if enrichment
                                else int(raw.get("employee_count") or 0)),
                tech_stack=(enrichment.tech_stack if enrichment
                            else raw.get("tech_stack", [])),
                engagement=kwargs.get("engagement", {}).get(lead.id, {}),
                weights=weights,
            )
            ctx.db.query(LeadScore).filter(LeadScore.lead_id == lead.id).delete()
            ctx.db.add(LeadScore(
                tenant_id=ctx.tenant_id, lead_id=lead.id, score=result["score"],
                band=result["band"], factors=result["factors"], weights=weights,
            ))
            lead.status = "scored"
            bands[result["band"]] = bands.get(result["band"], 0) + 1
            items.append({"lead_id": lead.id, "score": result["score"],
                          "band": result["band"]})

        ctx.db.flush()
        return AgentResult(
            output={"bands": bands, "items": items, "weights": weights},
            decision="SCORED", confidence=0.88,
            reason=", ".join(f"{count} {band}" for band, count in bands.items()) or "no leads scored",
        )
