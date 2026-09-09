"""Agent catalog, decision trace and workflow state — the Agent Monitor API."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import catalog
from app.core.deps import CurrentUser, get_current_user, get_db
from app.core.errors import NotFound
from app.models import AgentDecision, AgentExecution, AuditLog, WorkflowState

router = APIRouter()


@router.get("/catalog")
def agent_catalog():
    """The 13 agent responsibilities with role, inputs, strategy, output and stack."""
    return catalog()


@router.get("/executions")
def executions(workflow_id: str | None = None, agent: str | None = None,
               limit: int = Query(default=100, le=500),
               db: Session = Depends(get_db),
               user: CurrentUser = Depends(get_current_user)):
    stmt = (select(AgentExecution)
            .where(AgentExecution.tenant_id == user.tenant_id)
            .order_by(AgentExecution.created_at.desc()))
    if workflow_id:
        stmt = stmt.where(AgentExecution.workflow_id == workflow_id)
    if agent:
        stmt = stmt.where(AgentExecution.agent == agent)
    rows = db.scalars(stmt.limit(limit)).all()
    return [{"id": r.id, "workflow_id": r.workflow_id, "agent": r.agent,
             "node": r.node, "status": r.status, "latency_ms": r.latency_ms,
             "tokens": r.tokens, "cost_usd": r.cost_usd, "model": r.model,
             "error": r.error,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.get("/decisions")
def decisions(workflow_id: str | None = None, entity_id: str | None = None,
              limit: int = Query(default=100, le=500),
              db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    stmt = (select(AgentDecision)
            .where(AgentDecision.tenant_id == user.tenant_id)
            .order_by(AgentDecision.created_at.desc()))
    if workflow_id:
        stmt = stmt.where(AgentDecision.workflow_id == workflow_id)
    if entity_id:
        stmt = stmt.where(AgentDecision.entity_id == entity_id)
    rows = db.scalars(stmt.limit(limit)).all()
    return [{"id": r.id, "workflow_id": r.workflow_id, "agent": r.agent,
             "decision": r.decision, "confidence": r.confidence, "reason": r.reason,
             "entity_type": r.entity_type, "entity_id": r.entity_id,
             "model_or_rule_version": r.model_or_rule_version,
             "human_override": r.human_override,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.get("/workflows")
def workflows(limit: int = Query(default=50, le=200), db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(
        select(WorkflowState).where(WorkflowState.tenant_id == user.tenant_id)
        .order_by(WorkflowState.updated_at.desc()).limit(limit)).all()
    return [{"workflow_id": r.workflow_id, "status": r.status,
             "current_node": r.current_node, "paused_reason": r.paused_reason,
             "history": r.history[-12:] if r.history else []}
            for r in rows]


@router.get("/workflows/{workflow_id}")
def workflow_detail(workflow_id: str, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    row = db.scalar(select(WorkflowState).where(
        WorkflowState.workflow_id == workflow_id,
        WorkflowState.tenant_id == user.tenant_id))
    if not row:
        raise NotFound("Workflow not found")
    return {"workflow_id": row.workflow_id, "status": row.status,
            "current_node": row.current_node, "paused_reason": row.paused_reason,
            "state": row.state, "history": row.history}


@router.get("/audit")
def audit(limit: int = Query(default=100, le=500), db: Session = Depends(get_db),
          user: CurrentUser = Depends(get_current_user)):
    user.require("audit:read") if user.role in ("tenant_admin", "platform_admin") else None
    rows = db.scalars(
        select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
        .order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [{"id": r.id, "action": r.action, "actor": r.actor_name,
             "entity_type": r.entity_type, "entity_id": r.entity_id,
             "payload": r.payload,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]
