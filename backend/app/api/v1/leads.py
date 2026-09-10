"""Leads, verification workbench, enrichment, scoring and segmentation."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import AgentContext, get_agent
from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.errors import NotFound
from app.models import (
    AuditLog, Lead, LeadEnrichment, LeadExtraction, LeadScore, LeadVerification,
    Segment, SegmentMember,
)
from app.orchestration.state import new_workflow_id
from app.schemas.lead import (
    BulkResolution, ConflictResolution, LeadDetail, LeadOut, ScoreRequest,
    SegmentCreate,
)

router = APIRouter()


def _summarise(db: Session, lead: Lead) -> LeadOut:
    score = (db.query(LeadScore).filter(LeadScore.lead_id == lead.id)
             .order_by(LeadScore.created_at.desc()).first())
    enrichment = (db.query(LeadEnrichment)
                  .filter(LeadEnrichment.lead_id == lead.id).first())
    open_conflicts = (db.query(LeadVerification)
                      .filter(LeadVerification.lead_id == lead.id,
                              LeadVerification.status != "MATCH",
                              LeadVerification.resolved_value == "").count())
    return LeadOut(
        id=lead.id, full_name=lead.full_name, email=lead.email, title=lead.title,
        company_name=lead.company_name, location=lead.location,
        connector_key=lead.connector_key, status=lead.status,
        score=score.score if score else None, band=score.band if score else None,
        persona=enrichment.persona if enrichment else None,
        seniority=enrichment.seniority if enrichment else None,
        verification_status="open" if open_conflicts else "clear",
    )


@router.get("", response_model=list[LeadOut])
def list_leads(
    status: str | None = None,
    band: str | None = None,
    connector_key: str | None = None,
    min_score: int | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    stmt = select(Lead).where(Lead.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(Lead.status == status)
    if connector_key:
        stmt = stmt.where(Lead.connector_key == connector_key)
    if band or min_score is not None:
        stmt = stmt.join(LeadScore, LeadScore.lead_id == Lead.id)
        if band:
            stmt = stmt.where(LeadScore.band == band)
        if min_score is not None:
            stmt = stmt.where(LeadScore.score >= min_score)
    rows = db.scalars(stmt.offset(offset).limit(limit)).all()
    return [_summarise(db, lead) for lead in rows]


@router.get("/stats")
def lead_stats(db: Session = Depends(get_db),
               user: CurrentUser = Depends(get_current_user)):
    total = db.scalar(select(func.count(Lead.id))
                      .where(Lead.tenant_id == user.tenant_id)) or 0
    by_status = dict(db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.tenant_id == user.tenant_id).group_by(Lead.status)
    ).all())
    by_band = dict(db.execute(
        select(LeadScore.band, func.count(LeadScore.id))
        .where(LeadScore.tenant_id == user.tenant_id).group_by(LeadScore.band)
    ).all())
    by_source = dict(db.execute(
        select(Lead.connector_key, func.count(Lead.id))
        .where(Lead.tenant_id == user.tenant_id).group_by(Lead.connector_key)
    ).all())
    open_conflicts = db.scalar(
        select(func.count(LeadVerification.id)).where(
            LeadVerification.tenant_id == user.tenant_id,
            LeadVerification.status != "MATCH",
            LeadVerification.resolved_value == "",
        )
    ) or 0
    return {"total": total, "by_status": by_status, "by_band": by_band,
            "by_source": by_source, "open_conflicts": open_conflicts}


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: str, db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    lead = db.get(Lead, lead_id)
    if not lead or lead.tenant_id != user.tenant_id:
        raise NotFound("Lead not found")

    extraction = (db.query(LeadExtraction)
                  .filter(LeadExtraction.lead_id == lead.id)
                  .order_by(LeadExtraction.created_at.desc()).first())
    enrichment = (db.query(LeadEnrichment)
                  .filter(LeadEnrichment.lead_id == lead.id).first())
    score = (db.query(LeadScore).filter(LeadScore.lead_id == lead.id)
             .order_by(LeadScore.created_at.desc()).first())
    verifications = (db.query(LeadVerification)
                     .filter(LeadVerification.lead_id == lead.id).all())

    base = _summarise(db, lead)
    raw = lead.raw_payload or {}
    return LeadDetail(
        **base.model_dump(),
        profile_url=lead.profile_url,
        industry=(enrichment.industry if enrichment else raw.get("industry", "")),
        employee_count=(enrichment.employee_count if enrichment
                        else int(raw.get("employee_count") or 0)),
        raw_payload=raw,
        extraction=({"payload": extraction.payload, "confidence": extraction.confidence,
                     "status": extraction.status, "source": extraction.source}
                    if extraction else None),
        verifications=[{
            "id": v.id, "field": v.field, "uploaded_value": v.uploaded_value,
            "extracted_value": v.extracted_value, "status": v.status,
            "confidence": v.confidence, "reason": v.reason, "method": v.method,
            "resolved_value": v.resolved_value, "resolved_source": v.resolved_source,
            "resolved_by": v.resolved_by,
        } for v in verifications],
        enrichment=({"normalized_title": enrichment.normalized_title,
                     "seniority": enrichment.seniority, "function": enrichment.function,
                     "persona": enrichment.persona, "skills": enrichment.skills,
                     "tech_stack": enrichment.tech_stack,
                     "confidence": enrichment.confidence,
                     "duplicate_of": lead.duplicate_of_id}
                    if enrichment else None),
        score_detail=({"score": score.score, "band": score.band,
                       "factors": score.factors, "weights": score.weights}
                      if score else None),
    )


# -- verification workbench ------------------------------------------------
@router.get("/verification/queue")
def verification_queue(
    workflow_id: str | None = None,
    include_matches: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Field-level verification rows for the workbench.

    By default returns open conflicts only. Pass ``include_matches=true`` to
    also include MATCH / auto-accepted rows (snapshot-style reconciliation table).
    Optional ``workflow_id`` scopes rows to leads from the prior Agent 01 run.
    """
    stmt = (
        db.query(LeadVerification, Lead)
        .join(Lead, Lead.id == LeadVerification.lead_id)
        .filter(LeadVerification.tenant_id == user.tenant_id)
    )
    if workflow_id:
        stmt = stmt.filter(Lead.workflow_id == workflow_id)
    if not include_matches:
        stmt = stmt.filter(
            LeadVerification.status != "MATCH",
            LeadVerification.resolved_value == "",
        )
    rows = stmt.order_by(
        Lead.full_name.asc(),
        LeadVerification.field.asc(),
        LeadVerification.confidence.asc(),
    ).all()

    items = [{
        "verification_id": v.id,
        "lead_id": lead.id,
        "lead_name": lead.full_name,
        "company": lead.company_name,
        "field": v.field,
        "uploaded_value": v.uploaded_value,
        "extracted_value": v.extracted_value,
        "status": v.status,
        "confidence": v.confidence,
        "reason": v.reason,
        "method": v.method,
        "resolved_value": v.resolved_value or "",
        "resolved_source": v.resolved_source or "",
        "resolved_by": v.resolved_by or "",
        "workflow_id": lead.workflow_id or "",
    } for v, lead in rows]

    match = sum(1 for i in items if i["status"] == "MATCH")
    mismatch = sum(
        1 for i in items
        if i["status"] == "MISMATCH" and not i["resolved_value"]
    )
    needs_review = sum(
        1 for i in items
        if i["status"] == "NEEDS_REVIEW" and not i["resolved_value"]
    )
    resolved = sum(
        1 for i in items
        if i["resolved_source"] in ("uploaded", "extracted", "custom")
        and i["status"] != "MATCH"
    )
    return {
        "workflow_id": workflow_id or "",
        "stats": {
            "match": match,
            "mismatch": mismatch,
            "needs_review": needs_review,
            "resolved": resolved,
            "open": mismatch + needs_review,
            "total": len(items),
        },
        "items": items,
    }


@router.post("/verification/resolve")
def resolve_conflict(body: ConflictResolution, db: Session = Depends(get_db),
                     user: CurrentUser = Depends(require_permission("lead:write"))):
    row = db.get(LeadVerification, body.verification_id)
    if not row or row.tenant_id != user.tenant_id:
        raise NotFound("Verification record not found")

    value = {"uploaded": row.uploaded_value, "extracted": row.extracted_value}.get(
        body.resolution, body.custom_value
    )
    row.resolved_value = value
    row.resolved_source = body.resolution
    row.resolved_by = user.name or user.email
    row.resolved_at = datetime.now(timezone.utc)

    from app.orchestration.graph import LeadPipeline
    from app.services.telemetry import record_decision

    lead = db.get(Lead, row.lead_id)
    workflow_id = (lead.workflow_id if lead and lead.workflow_id else row.lead_id)

    # Apply the trusted value onto the lead so list/detail views stay in sync.
    if lead and row.field in ("title", "company_name", "location", "email", "phone"):
        setattr(lead, row.field, value or "")

    record_decision(
        db, tenant_id=user.tenant_id, workflow_id=workflow_id,
        agent="verification", decision=body.resolution.upper(), confidence=1.0,
        reason=f"Human resolution by {row.resolved_by}", entity_type="lead",
        entity_id=row.lead_id, version="verify-v1", human_override=True,
    )
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="verification.resolve", entity_type="lead_verification",
                    entity_id=row.id,
                    payload={"resolution": body.resolution, "value": value,
                             "workflow_id": workflow_id}))

    remaining = (db.query(LeadVerification)
                 .filter(LeadVerification.lead_id == row.lead_id,
                         LeadVerification.status != "MATCH",
                         LeadVerification.resolved_value == "").count())
    pipeline_state: dict = {}
    if lead and remaining == 0:
        lead.status = "verified"
        if lead.workflow_id:
            pipeline_state = LeadPipeline(
                db, user.tenant_id, lead.workflow_id, user.id, user.name
            ).resume()
    db.commit()
    return {
        "message": "Conflict resolved",
        "lead_id": row.lead_id,
        "remaining_conflicts": remaining,
        "workflow_id": workflow_id,
        "pipeline_status": pipeline_state.get("status"),
        "open_conflicts": pipeline_state.get("open_conflicts"),
    }


@router.post("/verification/bulk-resolve")
def bulk_resolve(body: BulkResolution, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(require_permission("lead:write"))):
    from app.orchestration.graph import LeadPipeline

    stmt = (db.query(LeadVerification)
            .filter(LeadVerification.tenant_id == user.tenant_id,
                    LeadVerification.status != "MATCH",
                    LeadVerification.resolved_value == ""))
    if body.lead_ids:
        stmt = stmt.filter(LeadVerification.lead_id.in_(body.lead_ids))
    rows = stmt.all()
    for row in rows:
        value = (row.extracted_value if body.resolution == "extracted"
                 else row.uploaded_value)
        row.resolved_value = value
        row.resolved_source = body.resolution
        row.resolved_by = user.name or user.email
        row.resolved_at = datetime.now(timezone.utc)
        lead = db.get(Lead, row.lead_id)
        if lead and row.field in ("title", "company_name", "location", "email", "phone"):
            setattr(lead, row.field, value or "")

    touched = {r.lead_id for r in rows}
    workflow_ids: set[str] = set()
    for lead_id in touched:
        lead = db.get(Lead, lead_id)
        if lead:
            lead.status = "verified"
            if lead.workflow_id:
                workflow_ids.add(lead.workflow_id)

    resumed = []
    for workflow_id in workflow_ids:
        state = LeadPipeline(
            db, user.tenant_id, workflow_id, user.id, user.name
        ).resume()
        resumed.append({"workflow_id": workflow_id, "status": state.get("status")})

    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="verification.bulk_resolve", entity_type="lead",
                    payload={"resolved": len(rows), "resolution": body.resolution,
                             "workflows_resumed": [r["workflow_id"] for r in resumed]}))
    db.commit()
    return {
        "resolved": len(rows),
        "leads_cleared": len(touched),
        "workflows_resumed": resumed,
    }


# -- pipeline steps --------------------------------------------------------
@router.post("/enrich")
def enrich(body: ScoreRequest, db: Session = Depends(get_db),
           user: CurrentUser = Depends(require_permission("lead:write"))):
    from app.models import LeadVerification

    leads = _resolve_leads(db, user, body.lead_ids, default_status="verified")
    # Hard gate: do not enrich while open conflicts remain.
    blocked_ids = {
        lead.id for lead in leads
        if db.query(LeadVerification).filter(
            LeadVerification.lead_id == lead.id,
            LeadVerification.status != "MATCH",
            LeadVerification.resolved_value == "",
        ).count()
    }
    leads = [lead for lead in leads if lead.id not in blocked_ids]
    if not leads:
        return {"enriched": 0, "skipped": len(blocked_ids),
                "message": "No verified leads without open conflicts"}
    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=new_workflow_id(), user_id=user.id,
                       user_name=user.name)
    result = get_agent("enrichment").run(ctx, leads=leads)
    db.commit()
    out = dict(result.output)
    out["skipped_open_conflicts"] = len(blocked_ids)
    return out


@router.post("/score")
def score(body: ScoreRequest, db: Session = Depends(get_db),
          user: CurrentUser = Depends(require_permission("lead:write"))):
    """Re-score with custom weights. Weights are not persisted unless you PUT the
    tenant policy — that keeps the 'move a slider in the demo' path side-effect
    free."""
    leads = _resolve_leads(db, user, body.lead_ids, default_status="enriched")
    if not leads:
        leads = _resolve_leads(db, user, body.lead_ids, default_status="scored")
    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=new_workflow_id(), user_id=user.id,
                       user_name=user.name)
    result = get_agent("scoring").run(ctx, leads=leads, weights=body.weights)
    db.commit()
    return result.output


@router.post("/segments/preview")
def preview_segments(body: SegmentCreate, db: Session = Depends(get_db),
                     user: CurrentUser = Depends(get_current_user)):
    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=new_workflow_id(), user_id=user.id,
                       user_name=user.name)
    result = get_agent("segmentation").run(
        ctx, min_score=body.min_score, group_by=body.group_by,
        min_size=body.min_size, industries=body.industries, persist=False,
    )
    db.rollback()
    return result.output


@router.post("/segments")
def create_segments(body: SegmentCreate, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_permission("campaign:write"))):
    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=new_workflow_id(), user_id=user.id,
                       user_name=user.name)
    result = get_agent("segmentation").run(
        ctx, min_score=body.min_score, group_by=body.group_by,
        min_size=body.min_size, industries=body.industries, persist=True,
    )
    db.commit()
    return result.output


@router.get("/segments/list")
def list_segments(db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(select(Segment).where(Segment.tenant_id == user.tenant_id)).all()
    return [{"id": s.id, "name": s.name, "description": s.description,
             "size": s.size, "method": s.method, "rules": s.rules,
             "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in rows]


@router.get("/segments/{segment_id}/members", response_model=list[LeadOut])
def segment_members(segment_id: str, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    leads = (db.query(Lead).join(SegmentMember, SegmentMember.lead_id == Lead.id)
             .filter(SegmentMember.segment_id == segment_id,
                     Lead.tenant_id == user.tenant_id).all())
    return [_summarise(db, lead) for lead in leads]


def _resolve_leads(db: Session, user: CurrentUser, lead_ids: list[str],
                   default_status: str | None = None) -> list[Lead]:
    stmt = select(Lead).where(Lead.tenant_id == user.tenant_id,
                              Lead.status != "policy_blocked")
    if lead_ids:
        stmt = stmt.where(Lead.id.in_(lead_ids))
    return list(db.scalars(stmt).all())
