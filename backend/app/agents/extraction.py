"""Agent 03 - Extraction.

Fetches the canonical view of a lead from its permitted source and stores it
*alongside* the uploaded values rather than over them. Verification needs both.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.connectors.demo_data import canonical_profile
from app.models import Lead, LeadExtraction
from app.services import policy


class ExtractionAgent(BaseAgent):
    key = "extraction"
    name = "Extraction"
    role = "Extracts structured profile data from approved sources"
    inputs = "Profile URL or source, source-policy configuration, tenant context"
    execution_strategy = (
        "Check source policy; fetch the approved source; parse; normalise; "
        "retry and rate-limit; persist the extracted snapshot."
    )
    outputs = "Structured profile, source metadata, extraction confidence and status"
    stack = "Playwright, parsers, Celery, Redis, PostgreSQL"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        leads: list[Lead] = kwargs["leads"]
        extracted, blocked = 0, 0
        details: list[dict] = []

        for lead in leads:
            allowed, why = policy.source_allowed(
                ctx.db, ctx.tenant_id, lead.source_connection_id
            )
            if not allowed:
                lead.status = "policy_blocked"
                ctx.db.add(LeadExtraction(
                    tenant_id=ctx.tenant_id, lead_id=lead.id,
                    source=lead.connector_key, status="policy_blocked",
                    error=why, confidence=0.0,
                ))
                blocked += 1
                details.append({"lead_id": lead.id, "status": "policy_blocked",
                                "reason": why})
                continue

            payload = self._extract(lead)
            confidence = 0.93 if payload.get("title") else 0.55
            ctx.db.add(LeadExtraction(
                tenant_id=ctx.tenant_id, lead_id=lead.id,
                source=lead.connector_key, payload=payload,
                confidence=confidence, status="extracted",
            ))
            lead.status = "extracted"
            extracted += 1
            details.append({"lead_id": lead.id, "status": "extracted",
                            "confidence": confidence})

        ctx.db.flush()
        return AgentResult(
            output={"extracted": extracted, "blocked": blocked, "details": details},
            decision="COMPLETE" if extracted else "BLOCKED",
            confidence=0.91,
            reason=f"{extracted} extracted, {blocked} blocked by source policy",
        )

    @staticmethod
    def _extract(lead: Lead) -> dict:
        """Return the canonical profile for a lead.

        Replace this method with the real source fetch for your deployment: a
        Playwright page render for allow-listed web sources, a CRM record read
        for Salesforce or HubSpot, or a vendor lookup for Apollo. The contract is
        the dict shape below; nothing downstream cares how it was obtained.
        """
        canonical = canonical_profile(lead.full_name)
        if canonical:
            return {**canonical, "source": lead.connector_key}
        raw = lead.raw_payload or {}
        return {
            "full_name": lead.full_name,
            "title": lead.title,
            "company_name": lead.company_name,
            "location": lead.location,
            "industry": raw.get("industry", ""),
            "employee_count": raw.get("employee_count", 0),
            "tech_stack": raw.get("tech_stack", []),
            "source": lead.connector_key,
        }
