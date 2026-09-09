"""LeadPipeline: extract → verify pause → resolve → resume → enrich → score."""
from __future__ import annotations

import io
import json

from app.agents import AgentContext, get_agent
from app.connectors.demo_data import demo_leads
from app.db.session import SessionLocal
from app.models import (
    IngestJob, Lead, LeadEnrichment, LeadScore, LeadVerification, Tenant,
    WorkflowState,
)
from app.orchestration.graph import LeadPipeline
from app.orchestration.state import new_workflow_id


def test_pipeline_pauses_on_conflicts_then_resumes_to_scoring():
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
        # People with deliberate title/company mismatches vs canonical_profile.
        raw = demo_leads("pipeline_test", limit=3)
        # Use unique emails so seed duplicates do not collapse the batch.
        for idx, lead in enumerate(raw):
            lead.email = f"pipeline.case{idx}@example.test"
            lead.external_id = f"pipeline-{idx}"

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


def test_upload_fixture_csv_pauses_for_human_review(client, auth):
    from pathlib import Path

    csv_path = Path(__file__).resolve().parents[1] / "fixtures" / "demo" / "saas_platform_targets.csv"
    content = csv_path.read_bytes()
    files = {"file": ("saas_platform_targets.csv", io.BytesIO(content), "text/csv")}
    resp = client.post(
        "/api/v1/sources/upload",
        files=files,
        data={"mapping_json": json.dumps({}), "run_pipeline": "true"},
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_valid"] >= 1
    # Demo people have title mismatches → pipeline should pause.
    assert body.get("open_conflicts", 0) > 0 or body.get("paused_at") == "verification"
