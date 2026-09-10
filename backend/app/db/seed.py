"""Seed a working demo: tenants, users, source connections, knowledge and leads.

Run with ``python -m app.db.seed`` or ``make seed``. Safe to re-run: it will not
duplicate a tenant that already exists.
"""
from __future__ import annotations

from sqlalchemy import select

from app.agents import AgentContext, get_agent
from app.connectors.demo_data import DEMO_DATA_ACTIVE, demo_leads
from app.core.logging import get_logger
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import (
    IngestJob, KnowledgeDocument, PolicyConfig, SourceConnection, Tenant, User,
)
from app.orchestration.graph import LeadPipeline
from app.orchestration.state import new_workflow_id
from app.services.policy import DEFAULT_SENDING_POLICY
from app.services.rag import index_document
from app.services.scoring import DEFAULT_WEIGHTS

log = get_logger("leadsense.seed")

TENANTS = [
    ("Feuji Revenue Operations", "feuji-revops"),
    ("Northwind Capital Partners", "northwind"),
]

USERS = [
    ("arnab.das@feuji.com", "Arnab Das", "sales_manager"),
    ("reviewer@feuji.com", "Sam Reviewer", "reviewer"),
    ("admin@feuji.com", "Tenant Admin", "tenant_admin"),
]

CONNECTIONS = [
    ("Spreadsheet uploads", "manual_upload", {}, True, "legitimate_interest"),
    ("Salesforce production", "salesforce", {"object": "Lead"}, True, "contract"),
    ("HubSpot marketing", "hubspot", {"lifecycle_stage": "lead"}, True, "consent"),
    ("ZoomInfo enrichment", "zoominfo", {}, True, "legitimate_interest"),
    ("Web profile public pages", "web_profile", {}, True, "legitimate_interest"),
    ("CSV feed URL/S3", "csv_url", {}, True, "legitimate_interest"),
    ("Apollo prospecting", "apollo",
     {"person_titles": "VP Operations, Head of Data, Chief Data Officer",
      "employee_ranges": "201,10000"}, True, "legitimate_interest"),
]

DOCUMENTS = [
    ("LeadSense platform brochure", "brochure", True,
     """LeadSense converts raw prospect information into verified, enriched, scored
and actionable sales intelligence.

Every lead is reconciled against its source before anyone contacts it. Teams
using verification-first outreach cut manual lead cleanup by roughly 70 percent
and stop working from records that were accurate eighteen months ago.

Governed AI agents create personalised campaigns, execute email outreach,
interpret engagement and recommend the next best sales action, with a human
approving every material step."""),
    ("Northbridge Bank case study", "case_study", True,
     """Northbridge Bank held 40,000 prospect records across three systems with no
agreement on which title was current.

Using LeadSense, the bank verified 40,000 records in eleven days. Sixty-one
percent matched automatically, twenty-two percent were corrected from the
extracted source, and the remainder went to a reviewer queue that two analysts
cleared in an afternoon.

Reply rates on the first campaign after verification were 2.4 times the
pre-verification baseline."""),
    ("RevOps data quality benchmark", "research", True,
     """Across surveyed B2B revenue teams, roughly one in three CRM contact records
carries a stale job title, and one in five carries a company name that no longer
matches the legal entity.

Teams that verify before personalising report materially lower bounce and
complaint rates, which is what protects sending-domain reputation over time."""),
    ("Unverified competitor comparison", "draft", False,
     """DRAFT - NOT APPROVED. This document claims LeadSense outperforms every rival
platform on accuracy. The claim is unsupported and must not be cited in outbound
material until it is substantiated and approved."""),
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        for name, slug in TENANTS:
            if db.scalar(select(Tenant).where(Tenant.slug == slug)):
                log.info("tenant %s already exists, skipping", slug)
                continue
            tenant = Tenant(name=name, slug=slug)
            db.add(tenant)
            db.flush()

            db.add(PolicyConfig(
                tenant_id=tenant.id, sending_policy=dict(DEFAULT_SENDING_POLICY),
                scoring_weights=dict(DEFAULT_WEIGHTS), campaign_threshold=70,
                source_policy={"web_profile": False, "broker_data": False},
            ))
            for email, user_name, role in USERS:
                db.add(User(tenant_id=tenant.id, email=email, name=user_name,
                            role=role))

            connections: dict[str, SourceConnection] = {}
            for conn_name, key, config, allowed, basis in CONNECTIONS:
                conn = SourceConnection(
                    tenant_id=tenant.id, name=conn_name, connector_key=key,
                    config_json=config, policy_allowed=allowed,
                    lawful_basis=basis, status="configured",
                )
                db.add(conn)
                db.flush()
                connections[key] = conn

            for title, doc_type, approved, content in DOCUMENTS:
                doc = KnowledgeDocument(
                    tenant_id=tenant.id, title=title, doc_type=doc_type,
                    content=content, approved=approved,
                    approved_by="Seed" if approved else "",
                )
                db.add(doc)
                db.flush()
                if approved:
                    index_document(db, doc)

            # Only the first tenant gets demo leads, so the second stays empty and
            # proves tenant isolation in a demo.
            if slug == TENANTS[0][1]:
                _seed_leads(db, tenant.id, connections)

            db.commit()
            log.info("seeded tenant %s", slug)

        log.info("seed complete")
    finally:
        db.close()


def _seed_leads(db, tenant_id: str, connections: dict) -> None:
    """Load leads from two different sources so the source layer is visible."""
    if not DEMO_DATA_ACTIVE:
        log.info("demo_data deactivated — skipping synthetic lead seed")
        return

    # Distinct slices per source, so the demo shows leads arriving from two
    # different systems rather than one system and six duplicates.
    for key, count, offset in (("salesforce", 6, 0), ("hubspot", 6, 6)):
        conn = connections.get(key)
        workflow_id = new_workflow_id()
        job = IngestJob(tenant_id=tenant_id, connector_key=key,
                        source_connection_id=conn.id if conn else None,
                        status="running")
        db.add(job)
        db.flush()

        raw = demo_leads(key, count, offset=offset)
        if not raw:
            log.info("no demo leads for %s — skip", key)
            continue
        ctx = AgentContext(db=db, tenant_id=tenant_id, workflow_id=workflow_id,
                           user_name="Seed")
        result = get_agent("ingestion").run(
            ctx, raw_leads=raw, job=job, connector_key=key,
            connection_id=conn.id if conn else None)

        lead_ids = result.output["lead_ids"]
        if lead_ids:
            LeadPipeline(db, tenant_id, workflow_id, user_name="Seed").run(lead_ids)
        log.info("seeded %d leads from %s", len(lead_ids), key)


if __name__ == "__main__":
    seed()
