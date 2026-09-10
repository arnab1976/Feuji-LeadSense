"""LeadPipeline: extract → verify pause → resolve → resume → enrich → score."""
from __future__ import annotations

from app.agents import AgentContext, get_agent
from app.agents.extraction import ExtractionAgent
from app.connectors.base import RawLead
from app.db.session import SessionLocal
from app.models import (
    IngestJob, Lead, LeadEnrichment, LeadScore, LeadVerification, Tenant,
    WorkflowState,
)
from app.orchestration.graph import LeadPipeline
from app.orchestration.state import new_workflow_id


def _sample_leads() -> list[RawLead]:
    return [
        RawLead(
            external_id="pipeline-0",
            full_name="Pipeline Case Zero",
            email="pipeline.case0@example.test",
            title="VP Operations",
            company_name="Northbridge Bank",
            location="Mumbai",
            industry="Banking",
            source="pipeline_test",
        ),
        RawLead(
            external_id="pipeline-1",
            full_name="Pipeline Case One",
            email="pipeline.case1@example.test",
            title="CTO",
            company_name="Aurum Capital",
            location="Singapore",
            industry="Asset management",
            source="pipeline_test",
        ),
        RawLead(
            external_id="pipeline-2",
            full_name="Pipeline Case Two",
            email="pipeline.case2@example.test",
            title="Head of Claims Technology",
            company_name="Vantage Insurance",
            location="London",
            industry="Insurance",
            source="pipeline_test",
        ),
    ]


def test_pipeline_pauses_on_conflicts_then_resumes_to_scoring(monkeypatch):
    """Human-gate path: inject field mismatches (demo_data is deactivated)."""
    real_extract = ExtractionAgent._extract

    def mismatched_extract(lead):
        payload = real_extract(lead)
        # Material differences so Verification opens conflicts.
        if payload.get("title"):
            payload["title"] = f"Expanded {payload['title']}"
        if payload.get("company_name"):
            payload["company_name"] = f"{payload['company_name']} Holdings Plc"
        return payload

    monkeypatch.setattr(ExtractionAgent, "_extract", staticmethod(mismatched_extract))

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == "feuji-revops").first()
        assert tenant is not None
        workflow_id = new_workflow_id()
        job = IngestJob(
            tenant_id=tenant.id, connector_key="manual_upload", status="running",
        )
        db.add(job)
        db.flush()

        ctx = AgentContext(
            db=db, tenant_id=tenant.id, workflow_id=workflow_id,
            user_id="test", user_name="Test",
        )
        raw = _sample_leads()

        ingested = get_agent("ingestion").run(
            ctx, raw_leads=raw, job=job, connector_key="manual_upload",
        )
        lead_ids = ingested.output["lead_ids"]
        assert len(lead_ids) >= 2

        get_agent("supervisor").run(
            ctx, node="ingestion",
            patch={"lead_ids": lead_ids, "handed_off_from": "ingestion"},
        )

        state = LeadPipeline(db, tenant.id, workflow_id, "test", "Test").run(lead_ids)
        assert state.get("status") == "paused"
        assert state.get("paused_at") == "verification"
        assert state.get("open_conflicts", 0) > 0
        assert state.get("awaiting_human_review") is True

        wf = db.query(WorkflowState).filter(
            WorkflowState.workflow_id == workflow_id
        ).first()
        assert wf is not None
        assert wf.status == "paused"
        nodes = [h.get("node") for h in (wf.history or [])]
        assert "ingestion" in nodes
        assert "pipeline.start" in nodes
        assert "extraction" in nodes
        assert "verification" in nodes

        # Enrichment must not have run while paused.
        assert db.query(LeadEnrichment).filter(
            LeadEnrichment.lead_id.in_(lead_ids)
        ).count() == 0

        open_rows = (
            db.query(LeadVerification)
            .filter(
                LeadVerification.lead_id.in_(lead_ids),
                LeadVerification.status != "MATCH",
                LeadVerification.resolved_value == "",
            )
            .all()
        )
        assert open_rows
        for row in open_rows:
            row.resolved_value = row.extracted_value or row.uploaded_value or "(resolved)"
            row.resolved_source = "extracted"
            row.resolved_by = "Test"
            lead = db.get(Lead, row.lead_id)
            if lead and row.field in ("title", "company_name", "location", "email"):
                setattr(lead, row.field, row.resolved_value)

        for lead_id in lead_ids:
            lead = db.get(Lead, lead_id)
            if lead:
                lead.status = "verified"

        db.flush()
        remaining = (
            db.query(LeadVerification)
            .filter(
                LeadVerification.lead_id.in_(lead_ids),
                LeadVerification.status != "MATCH",
                LeadVerification.resolved_value == "",
            )
            .count()
        )
        assert remaining == 0

        resumed = LeadPipeline(db, tenant.id, workflow_id, "test", "Test").resume()
        assert resumed.get("status") == "completed", resumed
        assert db.query(LeadEnrichment).filter(
            LeadEnrichment.lead_id.in_(lead_ids)
        ).count() >= 1
        assert db.query(LeadScore).filter(
            LeadScore.lead_id.in_(lead_ids)
        ).count() >= 1

        wf = db.query(WorkflowState).filter(
            WorkflowState.workflow_id == workflow_id
        ).first()
        assert wf.status == "completed"
        db.commit()
    finally:
        db.close()


def test_upload_fixture_csv_pauses_for_canonical_mismatches(client, auth):
    """BFSI fixture → canonical_profile → open verification conflicts."""
    resp = client.post(
        "/api/v1/sources/fixtures/run"
        "?filename=salesforce_bfsi_prospect_list.csv&limit=10&run_pipeline=true&connector_key=salesforce",
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_valid"] >= 1
    assert body.get("open_conflicts", 0) > 0 or body.get("paused_at") == "verification"