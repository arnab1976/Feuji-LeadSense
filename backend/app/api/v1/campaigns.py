"""Campaign creation, strategy planning and email generation."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentContext, get_agent
from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.errors import NotFound, ValidationFailure
from app.models import AuditLog, Campaign, GeneratedEmail, Lead, SegmentMember
from app.orchestration.state import new_workflow_id
from app.schemas.campaign import CampaignCreate, CampaignOut, GenerateEmailsRequest

router = APIRouter()


def _out(db: Session, campaign: Campaign) -> CampaignOut:
    count = db.query(GeneratedEmail).filter(
        GeneratedEmail.campaign_id == campaign.id).count()
    return CampaignOut(
        id=campaign.id, name=campaign.name, objective=campaign.objective,
        tone=campaign.tone, segment_id=campaign.segment_id, status=campaign.status,
        strategy=campaign.strategy or {}, email_count=count,
    )


@router.get("", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(select(Campaign).where(Campaign.tenant_id == user.tenant_id)).all()
    return [_out(db, c) for c in rows]


@router.post("", response_model=CampaignOut)
def create_campaign(body: CampaignCreate, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_permission("campaign:write"))):
    campaign = Campaign(
        tenant_id=user.tenant_id, name=body.name, objective=body.objective,
        tone=body.tone, segment_id=body.segment_id,
        knowledge_doc_ids=body.knowledge_doc_ids, workflow_id=new_workflow_id(),
    )
    db.add(campaign)
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="campaign.create", entity_type="campaign",
                    entity_id=campaign.id, payload={"name": body.name}))
    db.commit()
    db.refresh(campaign)
    return _out(db, campaign)


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.tenant_id != user.tenant_id:
        raise NotFound("Campaign not found")
    return _out(db, campaign)


@router.post("/{campaign_id}/strategy", response_model=CampaignOut)
def plan_strategy(campaign_id: str, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_permission("campaign:write"))):
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.tenant_id != user.tenant_id:
        raise NotFound("Campaign not found")
    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=campaign.workflow_id or new_workflow_id(),
                       user_id=user.id, user_name=user.name)
    get_agent("strategy").run(ctx, campaign=campaign)
    db.commit()
    db.refresh(campaign)
    return _out(db, campaign)


@router.post("/{campaign_id}/emails")
def generate_emails(campaign_id: str, body: GenerateEmailsRequest,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_permission("campaign:write"))):
    """Generate drafts, then immediately run the compliance gate over them."""
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.tenant_id != user.tenant_id:
        raise NotFound("Campaign not found")
    if not campaign.strategy:
        raise ValidationFailure(
            "Plan the campaign strategy before generating emails"
        )

    if body.lead_ids:
        leads = list(db.scalars(select(Lead).where(
            Lead.id.in_(body.lead_ids), Lead.tenant_id == user.tenant_id)).all())
    else:
        leads = (db.query(Lead)
                 .join(SegmentMember, SegmentMember.lead_id == Lead.id)
                 .filter(SegmentMember.segment_id == campaign.segment_id,
                         Lead.tenant_id == user.tenant_id).all())
    if not leads:
        raise ValidationFailure("No leads in this campaign's segment")

    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=campaign.workflow_id or new_workflow_id(),
                       user_id=user.id, user_name=user.name)
    generation = get_agent("email").run(ctx, campaign=campaign, leads=leads,
                                        regenerate=body.regenerate)

    emails = list(db.scalars(select(GeneratedEmail).where(
        GeneratedEmail.id.in_(generation.output["email_ids"]))).all())
    compliance = get_agent("compliance").run(ctx, emails=emails)

    campaign.status = "generated"
    db.commit()
    return {"generated": generation.output, "compliance": compliance.output}
