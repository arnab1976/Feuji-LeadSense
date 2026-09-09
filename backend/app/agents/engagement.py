"""Agent 12 - Engagement Intelligence."""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import (
    Campaign, EmailEvent, EmailSendJob, GeneratedEmail, Lead, LeadEnrichment, Reply,
)


class EngagementIntelligenceAgent(BaseAgent):
    key = "engagement"
    name = "Engagement Intelligence"
    role = "Analyses campaign performance and health"
    inputs = ("Delivery, bounce, complaint, click and reply events with segment "
              "and campaign context")
    execution_strategy = (
        "Aggregate metrics; detect high and low performing segments and variants; "
        "compute campaign health; generate recommendations."
    )
    outputs = "Campaign health, segment insights, variant recommendations, alerts"
    stack = "PostgreSQL or analytics store, Python aggregation, optional LLM summarisation"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        campaign: Campaign = kwargs["campaign"]

        emails = (ctx.db.query(GeneratedEmail)
                  .filter(GeneratedEmail.campaign_id == campaign.id).all())
        email_ids = [e.id for e in emails]

        sent = (ctx.db.query(EmailSendJob)
                .filter(EmailSendJob.email_id.in_(email_ids or [""]),
                        EmailSendJob.status == "sent").count())
        events = (ctx.db.query(EmailEvent)
                  .filter(EmailEvent.email_id.in_(email_ids or [""])).all())
        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1

        delivered = counts.get("delivered", 0)
        bounced = counts.get("bounced", 0)
        opened = counts.get("opened", 0)
        clicked = counts.get("clicked", 0)
        replies = (ctx.db.query(Reply)
                   .filter(Reply.email_id.in_(email_ids or [""])).all())
        positive = sum(1 for r in replies
                       if r.intent in ("MEETING_REQUEST", "INFORMATION_REQUEST",
                                       "REFERRAL"))

        def rate(numerator: int, denominator: int) -> float:
            return round(numerator / denominator, 4) if denominator else 0.0

        funnel = {
            "sent": sent, "delivered": delivered, "bounced": bounced,
            "opened": opened, "clicked": clicked, "replied": len(replies),
            "positive_intent": positive,
        }
        health = round(
            rate(delivered, max(sent, 1)) * 55 + rate(len(replies), max(delivered, 1)) * 45
        )

        # Per-segment reply performance, joined back to the enrichment persona.
        by_persona: dict[str, dict] = {}
        for email in emails:
            enrichment = (ctx.db.query(LeadEnrichment)
                          .filter(LeadEnrichment.lead_id == email.lead_id).first())
            persona = (enrichment.persona if enrichment else "") or "General business"
            bucket = by_persona.setdefault(persona, {"sent": 0, "replied": 0})
            bucket["sent"] += 1
            bucket["replied"] += sum(1 for r in replies if r.email_id == email.id)
        for bucket in by_persona.values():
            bucket["reply_rate"] = rate(bucket["replied"], bucket["sent"])

        # Subject-variant comparison.
        variants: dict[str, dict] = {}
        for email in emails:
            label = chr(65 + min(email.selected_variant, 2))
            bucket = variants.setdefault(label, {"sent": 0, "replied": 0})
            bucket["sent"] += 1
            bucket["replied"] += sum(1 for r in replies if r.email_id == email.id)
        for bucket in variants.values():
            bucket["reply_rate"] = rate(bucket["replied"], bucket["sent"])

        recommendations = self._recommend(funnel, by_persona, variants)

        return AgentResult(
            output={"funnel": funnel, "health": health, "by_persona": by_persona,
                    "variants": variants, "recommendations": recommendations,
                    "rates": {
                        "delivery": rate(delivered, max(sent, 1)),
                        "bounce": rate(bounced, max(sent, 1)),
                        "reply": rate(len(replies), max(delivered, 1)),
                    }},
            decision="HEALTHY" if health >= 60 else "NEEDS_ATTENTION",
            confidence=0.87,
            reason=f"health {health}, {sent} sent, {len(replies)} replies",
        )

    @staticmethod
    def _recommend(funnel, by_persona, variants) -> list[dict]:
        out: list[dict] = []
        if funnel["bounced"]:
            out.append({
                "recommendation": (f"Add {funnel['bounced']} bounced address(es) to "
                                   "the suppression list"),
                "confidence": 0.99, "status": "applied_automatically",
            })
        if len(variants) > 1:
            best = max(variants.items(), key=lambda kv: kv[1]["reply_rate"])
            out.append({
                "recommendation": (f"Shift remaining sequence volume to subject "
                                   f"variant {best[0]}"),
                "confidence": 0.81, "status": "awaiting_approval",
            })
        weak = [p for p, b in by_persona.items()
                if b["sent"] >= 3 and b["reply_rate"] == 0]
        for persona in weak:
            out.append({
                "recommendation": (f"Pause the {persona} segment and revisit the "
                                   "messaging theme"),
                "confidence": 0.7, "status": "awaiting_approval",
            })
        return out
