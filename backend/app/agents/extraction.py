"""Agent 03 - Extraction.

Persists a structured profile *alongside* the uploaded Lead so Verification can
compare the two. Starts from the ingested fields; when a demo canonical profile
is known for the company/title (fixture Verification demos), that becomes the
extracted snapshot so MATCH / MISMATCH / NEEDS_REVIEW can surface.
"""
from __future__ import annotations

import re

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.connectors.demo_data import canonical_profile
from app.models import Lead, LeadExtraction
from app.services import policy
from app.services.taxonomy import normalize_title

LEGAL_SUFFIXES = {
    "ltd", "limited", "plc", "inc", "corp", "gmbh", "ag", "sa", "as",
    "a/s", "ab", "kk", "sl", "pvt", "llc", "group", "partners", "co",
    "pjsc", "sas",
}


def normalize_company(name: str) -> str:
    """Strip legal suffixes and collapse whitespace for comparison/storage."""
    words = [w.strip(".,").lower() for w in (name or "").split()]
    kept = [w for w in words if w and w not in LEGAL_SUFFIXES]
    return " ".join(kept).title() if kept else (name or "").strip()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"[^\d+]", "", phone or "")
    return digits


class ExtractionAgent(BaseAgent):
    key = "extraction"
    name = "Extraction"
    summary = "Builds a canonical contact profile from raw rows"
    definition = (
        "Normalisation agent that turns RawLead rows into a consistent Lead "
        "profile with cleaned titles, companies, emails and phones."
    )
    description = (
        "Runs after Ingestion. Copies ingested person/company fields into "
        "LeadExtraction with light contact normalisation. For known demo "
        "fixture companies it applies canonical_profile expansions so the "
        "Verification bench can show field conflicts."
    )
    role = "Field cleaning · entity normalisation · profile assembly"
    stage = "2. Extraction"
    inputs = "RawLead[], connector field map, source-policy configuration, tenant context"
    execution_strategy = (
        "Check source policy; build extracted snapshot from the ingested lead; "
        "apply demo canonical_profile when the company/title is known; "
        "normalise contact fields; persist alongside the upload for Verification."
    )
    outputs = (
        "Structured profile (title, company, location, email, phone), "
        "normalised fields, source metadata, extraction confidence and status"
    )
    stack = "Playwright, parsers, Celery, Redis, PostgreSQL"
    version = "extraction-v1"

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
            if payload.get("email"):
                confidence = min(0.99, confidence + 0.02)
            ctx.db.add(LeadExtraction(
                tenant_id=ctx.tenant_id, lead_id=lead.id,
                source=lead.connector_key, payload=payload,
                confidence=confidence, status="extracted",
            ))
            lead.status = "extracted"
            extracted += 1
            details.append({
                "lead_id": lead.id,
                "status": "extracted",
                "confidence": confidence,
                "title": payload.get("title", ""),
                "company_name": payload.get("company_name", ""),
            })

        ctx.db.flush()
        return AgentResult(
            output={
                "extracted": extracted,
                "blocked": blocked,
                "details": details,
                "evidence": {"extracted": extracted, "blocked": blocked},
            },
            decision="COMPLETE" if extracted else "BLOCKED",
            confidence=0.91,
            reason=f"{extracted} extracted, {blocked} blocked by source policy",
        )

    @staticmethod
    def _extract(lead: Lead) -> dict:
        """Build extracted snapshot; apply demo canonical_profile when known."""
        raw = lead.raw_payload or {}
        email = normalize_email(lead.email or raw.get("email", ""))
        phone = normalize_phone(lead.phone or raw.get("phone", ""))

        canonical = canonical_profile(
            lead.full_name or "",
            title=lead.title or "",
            company_name=lead.company_name or "",
        )
        if canonical:
            title = canonical.get("title") or lead.title or ""
            company = canonical.get("company_name") or lead.company_name or ""
            location = canonical.get("location") or lead.location or ""
            return {
                "full_name": canonical.get("full_name") or lead.full_name,
                "title": title,
                "company_name": company,
                "location": location,
                "email": email,
                "phone": phone,
                "industry": canonical.get("industry") or raw.get("industry", ""),
                "employee_count": canonical.get("employee_count")
                or raw.get("employee_count", 0),
                "tech_stack": canonical.get("tech_stack")
                or raw.get("tech_stack", []),
                "normalized": {
                    "title": normalize_title(title),
                    "company_name": normalize_company(company),
                    "email": email,
                    "phone": phone,
                },
                "source": lead.connector_key,
                "canonical_applied": True,
            }

        title = lead.title or ""
        company = lead.company_name or ""
        return {
            "full_name": lead.full_name,
            "title": title,
            "company_name": company,
            "location": lead.location or "",
            "email": email,
            "phone": phone,
            "industry": raw.get("industry", ""),
            "employee_count": raw.get("employee_count", 0),
            "tech_stack": raw.get("tech_stack", []),
            "normalized": {
                "title": normalize_title(title),
                "company_name": normalize_company(company),
                "email": email,
                "phone": phone,
            },
            "source": lead.connector_key,
            "canonical_applied": False,
        }
