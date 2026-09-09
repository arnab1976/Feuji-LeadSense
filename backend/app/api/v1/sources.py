"""Source layer API.

This is where the connector abstraction becomes visible to the product: the
portal renders a settings form from ``config_fields``, tests the connection, and
syncs leads through one endpoint regardless of whether the source is a
spreadsheet, Salesforce, HubSpot or Apollo.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentContext, get_agent
from app.connectors import build_connector, list_connectors
from app.connectors.manual_upload import ManualUploadConnector
from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.errors import NotFound, ValidationFailure
from app.models import AuditLog, IngestJob, SourceConnection
from app.orchestration.graph import LeadPipeline
from app.orchestration.state import new_workflow_id
from app.schemas.source import (
    SourceConnectionCreate, SourceConnectionOut, SourceConnectionUpdate, SyncRequest,
    SyncResult,
)
from app.services import storage

router = APIRouter()

SECRET_MASK = "********"


def _mask(connector_key: str, config: dict) -> dict:
    from app.connectors import get_connector_class

    secret_names = {f.name for f in get_connector_class(connector_key).config_fields
                    if f.secret}
    return {k: (SECRET_MASK if k in secret_names and v else v)
            for k, v in (config or {}).items()}


def _out(conn: SourceConnection) -> SourceConnectionOut:
    from app.connectors import get_connector_class

    return SourceConnectionOut(
        id=conn.id, name=conn.name, connector_key=conn.connector_key,
        kind=get_connector_class(conn.connector_key).kind.value,
        status=conn.status, is_enabled=conn.is_enabled,
        policy_allowed=conn.policy_allowed, lawful_basis=conn.lawful_basis,
        last_sync_at=conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        last_error=conn.last_error,
        config=_mask(conn.connector_key, conn.config_json),
    )


# -- catalogue -------------------------------------------------------------
@router.get("/catalog")
def connector_catalog():
    """Every available connector with the settings form the portal should render."""
    return list_connectors()


# -- connections -----------------------------------------------------------
@router.get("/connections", response_model=list[SourceConnectionOut])
def list_connections(db: Session = Depends(get_db),
                     user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(
        select(SourceConnection).where(SourceConnection.tenant_id == user.tenant_id)
    ).all()
    return [_out(r) for r in rows]


@router.post("/connections", response_model=SourceConnectionOut)
def create_connection(body: SourceConnectionCreate, db: Session = Depends(get_db),
                      user: CurrentUser = Depends(require_permission("source:manage"))):
    from app.connectors import get_connector_class

    cls = get_connector_class(body.connector_key)  # raises NotFound on a bad key
    conn = SourceConnection(
        tenant_id=user.tenant_id, name=body.name, connector_key=body.connector_key,
        config_json=body.config,
        policy_allowed=body.policy_allowed and not cls.requires_policy_review
        if body.policy_allowed else False,
        lawful_basis=body.lawful_basis,
    )
    # A source flagged for policy review starts disallowed until a tenant admin
    # records a lawful basis, whatever the request asked for.
    if cls.requires_policy_review and body.lawful_basis in ("", "unknown", "none"):
        conn.policy_allowed = False
    db.add(conn)
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id,
                    actor_name=user.name, action="source.create",
                    entity_type="source_connection", entity_id=conn.id,
                    payload={"connector_key": body.connector_key}))
    db.commit()
    db.refresh(conn)
    return _out(conn)


@router.patch("/connections/{connection_id}", response_model=SourceConnectionOut)
def update_connection(connection_id: str, body: SourceConnectionUpdate,
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(require_permission("source:manage"))):
    conn = db.get(SourceConnection, connection_id)
    if not conn or conn.tenant_id != user.tenant_id:
        raise NotFound("Source connection not found")
    if body.name is not None:
        conn.name = body.name
    if body.config is not None:
        merged = dict(conn.config_json or {})
        merged.update({k: v for k, v in body.config.items() if v != SECRET_MASK})
        conn.config_json = merged
    if body.is_enabled is not None:
        conn.is_enabled = body.is_enabled
    if body.policy_allowed is not None:
        conn.policy_allowed = body.policy_allowed
    if body.lawful_basis is not None:
        conn.lawful_basis = body.lawful_basis
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="source.update", entity_type="source_connection",
                    entity_id=conn.id, payload=body.model_dump(exclude_none=True)))
    db.commit()
    db.refresh(conn)
    return _out(conn)


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: str, db: Session = Depends(get_db),
                      user: CurrentUser = Depends(require_permission("source:manage"))):
    conn = db.get(SourceConnection, connection_id)
    if not conn or conn.tenant_id != user.tenant_id:
        raise NotFound("Source connection not found")
    db.delete(conn)
    db.commit()
    return {"message": "Source connection removed"}


@router.post("/connections/{connection_id}/test")
def test_connection(connection_id: str, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_permission("source:manage"))):
    conn = db.get(SourceConnection, connection_id)
    if not conn or conn.tenant_id != user.tenant_id:
        raise NotFound("Source connection not found")
    connector = build_connector(conn.connector_key, conn.config_json, user.tenant_id)
    result = connector.test_connection()
    conn.status = "connected" if result.get("ok") else "error"
    conn.last_error = "" if result.get("ok") else str(result.get("message", ""))
    db.commit()
    return result


# -- sync ------------------------------------------------------------------
@router.post("/connections/{connection_id}/sync", response_model=SyncResult)
def sync_connection(connection_id: str, body: SyncRequest,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_permission("lead:write"))):
    """Pull leads from any configured connector and run the lead pipeline."""
    conn = db.get(SourceConnection, connection_id)
    if not conn or conn.tenant_id != user.tenant_id:
        raise NotFound("Source connection not found")
    if not conn.is_enabled:
        raise ValidationFailure(f"Source '{conn.name}' is disabled")

    connector = build_connector(conn.connector_key, conn.config_json, user.tenant_id)
    cursor = "" if body.reset_cursor else conn.last_sync_cursor
    fetched = connector.fetch(cursor=cursor, limit=body.limit)

    workflow_id = new_workflow_id()
    job = IngestJob(tenant_id=user.tenant_id, source_connection_id=conn.id,
                    connector_key=conn.connector_key, status="running")
    db.add(job)
    db.flush()

    ctx = AgentContext(db=db, tenant_id=user.tenant_id, workflow_id=workflow_id,
                       user_id=user.id, user_name=user.name)
    result = get_agent("ingestion").run(
        ctx, raw_leads=fetched.leads, job=job,
        connector_key=conn.connector_key, connection_id=conn.id,
    )

    conn.last_sync_at = datetime.now(timezone.utc)
    conn.last_sync_cursor = fetched.cursor or conn.last_sync_cursor
    conn.status = "connected"

    lead_ids = result.output["lead_ids"]
    if body.run_pipeline and lead_ids:
        LeadPipeline(db, user.tenant_id, workflow_id, user.id, user.name).run(lead_ids)

    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="source.sync", entity_type="source_connection",
                    entity_id=conn.id,
                    payload={"fetched": len(fetched.leads),
                             "created": len(lead_ids), "workflow_id": workflow_id}))
    db.commit()

    return SyncResult(
        job_id=job.id, connector_key=conn.connector_key,
        fetched=len(fetched.leads), created=len(lead_ids),
        duplicates=result.output["rows_duplicate"],
        invalid=result.output["rows_invalid"],
        cursor=fetched.cursor, warnings=fetched.warnings,
    )


# -- manual upload ---------------------------------------------------------
@router.post("/upload/preview")
async def preview_upload(file: UploadFile = File(...),
                         user: CurrentUser = Depends(require_permission("lead:write"))):
    """Parse a file without saving anything, so the user can confirm the mapping."""
    content = await file.read()
    connector = ManualUploadConnector(tenant_id=user.tenant_id)
    leads, report = connector.parse(content, file.filename or "upload.csv")
    return {
        "headers": report["headers"],
        "mapping": report["mapping"],
        "unmapped_headers": report["unmapped_headers"],
        "rows_detected": report["rows_read"],
        "rows_invalid": report["rows_invalid"],
        "sample_rows": [
            {"full_name": lead.full_name, "email": lead.email, "title": lead.title,
             "company_name": lead.company_name, "location": lead.location}
            for lead in leads[:5]
        ],
    }


@router.post("/upload")
async def upload_leads(
    file: UploadFile = File(...),
    mapping_json: str = Form(default="{}"),
    run_pipeline: bool = Form(default=True),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("lead:write")),
):
    """Ingest an uploaded file and run the lead pipeline over the new records."""
    import json

    content = await file.read()
    filename = file.filename or "upload.csv"
    try:
        mapping = json.loads(mapping_json or "{}")
    except json.JSONDecodeError:
        raise ValidationFailure("mapping_json is not valid JSON")

    connector = ManualUploadConnector(tenant_id=user.tenant_id)
    leads, report = connector.parse(content, filename, mapping or None)

    storage_key = storage.save(f"{user.tenant_id}/uploads/{filename}", content)
    workflow_id = new_workflow_id()

    conn = db.scalar(
        select(SourceConnection).where(
            SourceConnection.tenant_id == user.tenant_id,
            SourceConnection.connector_key == "manual_upload",
        )
    )
    job = IngestJob(tenant_id=user.tenant_id, connector_key="manual_upload",
                    filename=filename, storage_key=storage_key,
                    mapping=report["mapping"], status="running",
                    source_connection_id=conn.id if conn else None)
    db.add(job)
    db.flush()

    ctx = AgentContext(db=db, tenant_id=user.tenant_id, workflow_id=workflow_id,
                       user_id=user.id, user_name=user.name)
    result = get_agent("ingestion").run(
        ctx, raw_leads=leads, job=job, connector_key="manual_upload",
        connection_id=conn.id if conn else None,
    )
    job.rows_invalid += report["rows_invalid"]

    lead_ids = result.output["lead_ids"]
    pipeline_state = {}
    if run_pipeline and lead_ids:
        pipeline_state = LeadPipeline(
            db, user.tenant_id, workflow_id, user.id, user.name
        ).run(lead_ids)

    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="lead.upload", entity_type="ingest_job", entity_id=job.id,
                    payload={"filename": filename, "rows": report["rows_read"]}))
    db.commit()

    return {
        "job_id": job.id,
        "workflow_id": workflow_id,
        "rows_read": report["rows_read"],
        "rows_valid": result.output["rows_valid"],
        "rows_invalid": job.rows_invalid,
        "rows_duplicate": result.output["rows_duplicate"],
        "errors": (report["errors"] + result.output["errors"])[:50],
        "lead_ids": lead_ids,
        "mapping": report["mapping"],
        "paused_at": pipeline_state.get("paused_at"),
        "open_conflicts": pipeline_state.get("open_conflicts", 0),
    }
