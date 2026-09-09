"""Agent 13 - Reply Intelligence and Next Best Action."""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import Lead, LeadScore, Reply, SourceConnection
from app.services import policy
from app.services.llm import llm

SYSTEM = ("You classify B2B sales replies. Reply with JSON only using keys intent, "
          "confidence, score_delta, next_action, requires_human. Valid intents: "
          "MEETING_REQUEST, INFORMATION_REQUEST, NOT_NOW, UNSUBSCRIBE, REFERRAL, "
          "NEGATIVE, UNCLEAR.")

CRM_BY_INTENT = {
    "MEETING_REQUEST": {"object": "Task", "subject": "Schedule discovery call",
                        "priority": "High", "owner": "Account owner"},
    "INFORMATION_REQUEST": {"object": "Task", "subject": "Send approved material",
                            "priority": "Medium", "owner": "Sales development"},
    "NOT_NOW": {"object": "Lead", "subject": "Set nurture date",
                "priority": "Low", "owner": "Marketing"},
    "UNSUBSCRIBE": {"object": "Contact", "subject": "Suppress - explicit opt-out",
                    "priority": "Immediate", "owner": "System"},
    "REFERRAL": {"object": "Contact", "subject": "Create referred contact and re-verify",
                 "priority": "High", "owner": "Sales development"},
    "NEGATIVE": {"object": "Lead", "subject": "Mark disqualified",
                 "priority": "Low", "owner": "Sales development"},
    "UNCLEAR": {"object": "Task", "subject": "Human review of reply",
                "priority": "Medium", "owner": "Sales development"},
}


class ReplyIntelligenceAgent(BaseAgent):
    key = "reply"
    name = "Reply Intelligence + Next Best Action"
    role = "Classifies replies and recommends governed follow-up"
    inputs = "Prospect reply, prior sequence, lead score, campaign context, CRM state"
    execution_strategy = (
        "Classify intent; extract the requested action; update engagement features "
        "and score; decide stop, nurture, notify, schedule or CRM task; require a "
        "human gate for sensitive actions."
    )
    outputs = "Reply intent, confidence, score change, next action, CRM payload"
    stack = "LLM or classifier, LangGraph, rules, MCP and API integrations"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        lead: Lead = kwargs["lead"]
        body: str = kwargs["body"]
        email_id: str | None = kwargs.get("email_id")

        prompt = (f"Classify the reply below.\nreply_intent required.\n"
                  f"Lead: {lead.full_name}, {lead.title} at {lead.company_name}\n"
                  f"Reply:\n{body}\n")
        response = llm.complete(prompt, system=SYSTEM, max_tokens=500, temperature=0.1)
        try:
            parsed = response.json()
        except Exception:
            parsed = {"intent": "UNCLEAR", "confidence": 0.3, "score_delta": 0,
                      "next_action": "Route to a human for reading",
                      "requires_human": True}

        intent = parsed.get("intent", "UNCLEAR")
        delta = int(parsed.get("score_delta", 0))

        # Update the lead score so engagement feeds back into prioritisation.
        score_row = (ctx.db.query(LeadScore)
                     .filter(LeadScore.lead_id == lead.id)
                     .order_by(LeadScore.created_at.desc()).first())
        if score_row and delta:
            from app.services.scoring import band_for
            score_row.score = max(0, min(100, score_row.score + delta))
            score_row.band = band_for(score_row.score)

        # UNSUBSCRIBE is executed immediately: it is a legal obligation, not a
        # recommendation, and it is the one action that needs no human gate.
        if intent == "UNSUBSCRIBE" and lead.email:
            policy.suppress(ctx.db, ctx.tenant_id, lead.email,
                            reason="unsubscribe_request", source="reply")

        crm_payload = dict(CRM_BY_INTENT.get(intent, CRM_BY_INTENT["UNCLEAR"]))
        crm_payload.update({
            "lead_id": lead.id, "workflow_id": ctx.workflow_id,
            "via": self._crm_route(ctx, lead),
        })

        requires_human = bool(parsed.get("requires_human", False))
        reply = Reply(
            tenant_id=ctx.tenant_id, email_id=email_id, lead_id=lead.id, body=body,
            intent=intent, confidence=float(parsed.get("confidence", 0.5)),
            score_delta=delta, next_action=parsed.get("next_action", ""),
            requires_human=requires_human,
            action_status="proposed" if requires_human else "executed",
            crm_payload=crm_payload,
        )
        ctx.db.add(reply)
        ctx.db.flush()

        return AgentResult(
            output={"reply_id": reply.id, "intent": intent,
                    "score_delta": delta, "crm_payload": crm_payload,
                    "next_action": reply.next_action},
            decision=intent, confidence=reply.confidence,
            reason=reply.next_action, requires_human=requires_human,
            pause_reason="nba_approval" if requires_human else "",
            tokens=response.tokens, cost_usd=response.cost_usd, model=response.model,
        )

    @staticmethod
    def _crm_route(ctx: AgentContext, lead: Lead) -> str:
        """Prefer writing back to the CRM the lead actually came from."""
        if lead.source_connection_id:
            conn = ctx.db.get(SourceConnection, lead.source_connection_id)
            if conn and conn.connector_key in ("salesforce", "hubspot"):
                return f"connector:{conn.connector_key}"
        crm = (ctx.db.query(SourceConnection)
               .filter(SourceConnection.tenant_id == ctx.tenant_id,
                       SourceConnection.connector_key.in_(["salesforce", "hubspot"]),
                       SourceConnection.is_enabled.is_(True)).first())
        return f"connector:{crm.connector_key}" if crm else "none"
