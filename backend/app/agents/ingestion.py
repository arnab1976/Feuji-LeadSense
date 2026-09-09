"""Agent 02 - Lead Ingestion.

Entry point for every RawLead[] from the seven source connectors
(Salesforce, HubSpot, Manual Upload, ZoomInfo, Web Profile, CSV Feed, Apollo).

Architecture:
  Frontend / API → Upload CSV / Sync CRM
  → Validate, dedupe, persist leads
  → return lead_ids + job stats
  → LeadPipeline.run(lead_ids) with Workflow Orchestrator checkpoints
"""
from __future__ import annotations

from sqlalchemy import select

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.connectors.base import RawLead
from app.models import IngestJob, Lead

# Built-in connectors that feed this agent (architecture diagram).
SOURCE_CONNECTORS = (
    "salesforce",
    "hubspot",
    "manual_upload",
    "zoominfo",
    "web_profile",
    "csv_url",
    "apollo",
)


class LeadIngestionAgent(BaseAgent):
    key = "ingestion"
    name = "Lead Ingestion"
    summary = "Receives and validates bulk lead information"
    definition = (
        "Entry agent that accepts connector payloads and file uploads, then "
        "produces a durable RawLead batch for the orchestrated pipeline."
    )
    description = (
        "Owns the Source → RawLead hand-off. It validates tenant mapping rules, "
        "detects columns, normalises row syntax, collapses duplicates, and "
        "creates the ingestion job before the Orchestrator starts Extraction."
    )
    role = "Batch intake · schema gate · dedupe · persistence"
    stage = "1. Lead upload"
    inputs = (
        "CSV/Excel upload, CRM or API payload, tenant mapping rules; "
        "RawLead[] from Salesforce / HubSpot / Manual CSV-Excel / ZoomInfo / "
        "Web Profile / CSV Feed-S3 / Apollo.io"
    )
    execution_strategy = (
        "Validate file and schema; detect columns; map fields; validate syntax; "
        "dedupe; create the batch job; persist records; queue background work."
    )
    outputs = (
        "job_id, lead_ids, valid / invalid / duplicate counts, "
        "normalised lead records, connector_key"
    )
    stack = "FastAPI, Pandas, OpenPyXL, Pydantic, Celery, Redis, PostgreSQL, S3"
    version = "ingestion-v1"

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        raw_leads: list[RawLead] = kwargs["raw_leads"]
        job: IngestJob = kwargs["job"]
        connector_key: str = kwargs.get("connector_key", "manual_upload")
        connection_id: str | None = kwargs.get("connection_id")

        existing = {
            key for (key,) in ctx.db.execute(
                select(Lead.dedupe_key).where(Lead.tenant_id == ctx.tenant_id)
            ).all() if key
        }

        created: list[Lead] = []
        duplicates = 0
        invalid = 0
        errors: list[dict] = []
        seen_in_batch: set[str] = set()

        for raw in raw_leads:
            ok, reason = raw.is_valid()
            if not ok:
                invalid += 1
                errors.append({"external_id": raw.external_id, "reason": reason})
                continue
            key = raw.dedupe_key()
            if key in existing or key in seen_in_batch:
                duplicates += 1
                continue
            seen_in_batch.add(key)

            lead = Lead(
                tenant_id=ctx.tenant_id, ingest_job_id=job.id,
                source_connection_id=connection_id, connector_key=connector_key,
                external_id=raw.external_id, full_name=raw.full_name,
                email=raw.email, title=raw.title, company_name=raw.company_name,
                location=raw.location, profile_url=raw.profile_url, phone=raw.phone,
                raw_payload={**raw.raw, "industry": raw.industry,
                             "employee_count": raw.employee_count,
                             "tech_stack": raw.tech_stack},
                dedupe_key=key, status="ingested", workflow_id=ctx.workflow_id,
            )
            ctx.db.add(lead)
            created.append(lead)

        ctx.db.flush()

        job.rows_read = len(raw_leads)
        job.rows_valid = len(created)
        job.rows_invalid = invalid
        job.rows_duplicate = duplicates
        job.errors = errors[:100]
        job.status = "completed"
        job.connector_key = connector_key

        lead_ids = [lead.id for lead in created]
        stats = {
            "job_id": job.id,
            "connector_key": connector_key,
            "lead_ids": lead_ids,
            "rows_read": len(raw_leads),
            "rows_valid": len(created),
            "rows_invalid": invalid,
            "rows_duplicate": duplicates,
            "errors": errors[:50],
            "source_connectors": list(SOURCE_CONNECTORS),
            "evidence": {
                "connector_key": connector_key,
                "validated": len(raw_leads) - invalid,
                "persisted": len(created),
                "duplicates": duplicates,
                "invalid": invalid,
            },
        }

        return AgentResult(
            output=stats,
            decision="ACCEPTED" if created else "REJECTED",
            confidence=0.97,
            reason=(
                f"Validate/dedupe/persist via {connector_key}: "
                f"{len(created)} valid, {duplicates} duplicate, "
                f"{invalid} invalid of {len(raw_leads)} rows"
            ),
        )
