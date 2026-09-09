"""Campaign analytics and the executive dashboard."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import AgentContext, get_agent
from app.core.deps import CurrentUser, get_current_user, get_db
from app.core.errors import NotFound
from app.models import (
    AgentExecution, Campaign, EmailSendJob, GeneratedEmail, Lead, LeadScore,
    LeadVerification, Reply, SourceConnection,
)
from app.orchestration.state import new_workflow_id

router = APIRouter()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    tid = user.tenant_id
    leads = db.scalar(select(func.count(Lead.id)).where(Lead.tenant_id == tid)) or 0
    qualified = db.scalar(
        select(func.count(LeadScore.id)).where(LeadScore.tenant_id == tid,
                                               LeadScore.score >= 70)) or 0
    campaigns = db.scalar(
        select(func.count(Campaign.id)).where(Campaign.tenant_id == tid)) or 0
    sent = db.scalar(
        select(func.count(EmailSendJob.id)).where(EmailSendJob.tenant_id == tid,
                                                  EmailSendJob.status == "sent")) or 0
    replies = db.scalar(select(func.count(Reply.id)).where(Reply.tenant_id == tid)) or 0
    open_conflicts = db.scalar(
        select(func.count(LeadVerification.id)).where(
            LeadVerification.tenant_id == tid,
            LeadVerification.status != "MATCH",
            LeadVerification.resolved_value == "")) or 0
    bands = dict(db.execute(
        select(LeadScore.band, func.count(LeadScore.id))
        .where(LeadScore.tenant_id == tid).group_by(LeadScore.band)).all())
    sources = dict(db.execute(
        select(Lead.connector_key, func.count(Lead.id))
        .where(Lead.tenant_id == tid).group_by(Lead.connector_key)).all())
    connections = db.scalar(
        select(func.count(SourceConnection.id)).where(
            SourceConnection.tenant_id == tid,
            SourceConnection.is_enabled.is_(True))) or 0

    return {
        "leads": leads, "qualified": qualified, "campaigns": campaigns,
        "emails_sent": sent, "replies": replies, "open_conflicts": open_conflicts,
        "bands": bands, "leads_by_source": sources, "active_connections": connections,
    }


@router.get("/campaigns/{campaign_id}")
def campaign_analytics(campaign_id: str, db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.tenant_id != user.tenant_id:
        raise NotFound("Campaign not found")
    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=campaign.workflow_id or new_workflow_id(),
                       user_id=user.id, user_name=user.name)
    result = get_agent("engagement").run(ctx, campaign=campaign)
    db.commit()
    return result.output


@router.get("/costs")
def cost_summary(db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    """Token and cost telemetry per agent — instrumented from build one."""
    rows = db.execute(
        select(AgentExecution.agent, func.count(AgentExecution.id),
               func.sum(AgentExecution.tokens), func.sum(AgentExecution.cost_usd),
               func.avg(AgentExecution.latency_ms))
        .where(AgentExecution.tenant_id == user.tenant_id)
        .group_by(AgentExecution.agent)).all()
    emails = db.scalar(
        select(func.count(GeneratedEmail.id)).where(
            GeneratedEmail.tenant_id == user.tenant_id)) or 0
    total_cost = sum(float(r[3] or 0) for r in rows)
    return {
        "by_agent": [{"agent": r[0], "calls": r[1], "tokens": int(r[2] or 0),
                      "cost_usd": round(float(r[3] or 0), 6),
                      "avg_latency_ms": round(float(r[4] or 0))} for r in rows],
        "total_cost_usd": round(total_cost, 6),
        "emails_generated": emails,
        "cost_per_email": round(total_cost / emails, 6) if emails else 0.0,
    }
