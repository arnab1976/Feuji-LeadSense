"""Reply intelligence and next-best-action execution."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentContext, get_agent
from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.errors import NotFound
from app.connectors import build_connector
from app.models import AuditLog, Lead, Reply, SourceConnection
from app.orchestration.state import new_workflow_id
from app.schemas.campaign import ReplyIn, ReplyOut

router = APIRouter()


def _out(reply: Reply) -> ReplyOut:
    return ReplyOut(
        id=reply.id, lead_id=reply.lead_id, body=reply.body, intent=reply.intent,
        confidence=reply.confidence, score_delta=reply.score_delta,
        next_action=reply.next_action, requires_human=reply.requires_human,
        action_status=reply.action_status, crm_payload=reply.crm_payload or {},
    )


@router.get("", response_model=list[ReplyOut])
def list_replies(db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(select(Reply).where(Reply.tenant_id == user.tenant_id)).all()
    return [_out(r) for r in rows]


@router.post("", response_model=ReplyOut)
def ingest_reply(body: ReplyIn, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(require_permission("campaign:write"))):
    """Classify an inbound reply and propose the next action."""
    lead = db.get(Lead, body.lead_id)
    if not lead or lead.tenant_id != user.tenant_id:
        raise NotFound("Lead not found")

    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=lead.workflow_id or new_workflow_id(),
                       user_id=user.id, user_name=user.name)
    result = get_agent("reply").run(ctx, lead=lead, body=body.body,
                                    email_id=body.email_id)
    db.commit()
    reply = db.get(Reply, result.output["reply_id"])
    return _out(reply)


@router.post("/{reply_id}/execute")
def execute_action(reply_id: str, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(require_permission("campaign:write"))):
    """Human approval of a proposed next-best action, then CRM write-back."""
    reply = db.get(Reply, reply_id)
    if not reply or reply.tenant_id != user.tenant_id:
        raise NotFound("Reply not found")

    route = (reply.crm_payload or {}).get("via", "none")
    pushed: dict = {"routed": route}
    if route.startswith("connector:"):
        key = route.split(":", 1)[1]
        conn = db.scalar(select(SourceConnection).where(
            SourceConnection.tenant_id == user.tenant_id,
            SourceConnection.connector_key == key,
            SourceConnection.is_enabled.is_(True)))
        if conn:
            connector = build_connector(key, conn.config_json, user.tenant_id)
            lead = db.get(Lead, reply.lead_id)
            pushed = connector.push([{
                "external_id": lead.external_id if lead else "",
                "subject": reply.crm_payload.get("subject", "LeadSense follow-up"),
                "description": reply.next_action,
                "priority": reply.crm_payload.get("priority", "Normal"),
            }])
            pushed["routed"] = route

    reply.action_status = "executed"
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="nba.execute", entity_type="reply", entity_id=reply.id,
                    payload={"intent": reply.intent, "push": pushed}))
    db.commit()
    return {"reply_id": reply.id, "action_status": reply.action_status,
            "crm_result": pushed}


@router.post("/{reply_id}/reject")
def reject_action(reply_id: str, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_permission("campaign:write"))):
    reply = db.get(Reply, reply_id)
    if not reply or reply.tenant_id != user.tenant_id:
        raise NotFound("Reply not found")
    reply.action_status = "rejected"
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="nba.reject", entity_type="reply", entity_id=reply.id,
                    payload={"intent": reply.intent}))
    db.commit()
    return {"reply_id": reply.id, "action_status": reply.action_status}
