"""Background tasks: bulk pipelines, scheduled source syncs, campaign sends."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents import AgentContext, get_agent
from app.connectors import build_connector
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import GeneratedEmail, IngestJob, SourceConnection
from app.orchestration.graph import LeadPipeline
from app.orchestration.state import new_workflow_id
from app.workers.celery_app import celery

log = get_logger("leadsense.worker")


@celery.task(name="leadsense.run_lead_pipeline", bind=True, max_retries=3)
def run_lead_pipeline(self, tenant_id: str, lead_ids: list[str],
                      workflow_id: str = "", user_id: str = ""):
    """Extraction -> verification -> enrichment -> scoring for a lead batch."""
    db = SessionLocal()
    try:
        wf = workflow_id or new_workflow_id()
        state = LeadPipeline(db, tenant_id, wf, user_id).run(lead_ids)
        db.commit()
        return {"workflow_id": wf, "paused_at": state.get("paused_at"),
                "open_conflicts": state.get("open_conflicts", 0)}
    except Exception as exc:
        db.rollback()
        log.exception("lead pipeline failed")
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()


@celery.task(name="leadsense.sync_source", bind=True, max_retries=3)
def sync_source(self, tenant_id: str, connection_id: str, limit: int = 100):
    """Pull a page from one connector and run the pipeline over new leads."""
    db = SessionLocal()
    try:
        conn = db.get(SourceConnection, connection_id)
        if not conn or not conn.is_enabled:
            return {"skipped": True, "reason": "connection missing or disabled"}

        connector = build_connector(conn.connector_key, conn.config_json, tenant_id)
        fetched = connector.fetch(cursor=conn.last_sync_cursor, limit=limit)

        workflow_id = new_workflow_id()
        job = IngestJob(tenant_id=tenant_id, source_connection_id=conn.id,
                        connector_key=conn.connector_key, status="running")
        db.add(job)
        db.flush()

        ctx = AgentContext(db=db, tenant_id=tenant_id, workflow_id=workflow_id)
        result = get_agent("ingestion").run(
            ctx, raw_leads=fetched.leads, job=job,
            connector_key=conn.connector_key, connection_id=conn.id)

        conn.last_sync_at = datetime.now(timezone.utc)
        conn.last_sync_cursor = fetched.cursor or conn.last_sync_cursor
        conn.last_error = ""

        lead_ids = result.output["lead_ids"]
        if lead_ids:
            LeadPipeline(db, tenant_id, workflow_id).run(lead_ids)
        db.commit()
        return {"connector": conn.connector_key, "fetched": len(fetched.leads),
                "created": len(lead_ids), "workflow_id": workflow_id}
    except Exception as exc:
        db.rollback()
        conn = db.get(SourceConnection, connection_id)
        if conn:
            conn.last_error = str(exc)[:500]
            conn.status = "error"
            db.commit()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


@celery.task(name="leadsense.sync_all_sources")
def sync_all_sources():
    """Beat task: sync every enabled, policy-allowed connection."""
    db = SessionLocal()
    try:
        rows = db.scalars(select(SourceConnection).where(
            SourceConnection.is_enabled.is_(True),
            SourceConnection.policy_allowed.is_(True))).all()
        dispatched = []
        for conn in rows:
            if conn.connector_key == "manual_upload":
                continue  # nothing to poll
            sync_source.delay(conn.tenant_id, conn.id)
            dispatched.append(conn.id)
        return {"dispatched": dispatched}
    finally:
        db.close()


@celery.task(name="leadsense.send_campaign", bind=True, max_retries=2)
def send_campaign(self, tenant_id: str, email_ids: list[str], user_id: str = "",
                  user_name: str = ""):
    """Send approved emails. The agent still refuses anything without approval."""
    db = SessionLocal()
    try:
        emails = list(db.scalars(select(GeneratedEmail).where(
            GeneratedEmail.id.in_(email_ids),
            GeneratedEmail.tenant_id == tenant_id)).all())
        ctx = AgentContext(db=db, tenant_id=tenant_id,
                           workflow_id=new_workflow_id(), user_id=user_id,
                           user_name=user_name)
        result = get_agent("execution").run(ctx, emails=emails)
        db.commit()
        return result.output
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=45)
    finally:
        db.close()
