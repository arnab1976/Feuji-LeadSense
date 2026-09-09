"""Email review, approval and send. The human gate lives here."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentContext, get_agent
from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.errors import NotFound, PolicyViolation
from app.models import (
    AuditLog, ComplianceCheck, EmailApproval, GeneratedEmail, Lead,
)
from app.orchestration.state import new_workflow_id
from app.schemas.campaign import ApprovalRequest, EmailEdit, EmailOut, SendRequest

router = APIRouter()


def _out(db: Session, email: GeneratedEmail) -> EmailOut:
    lead = db.get(Lead, email.lead_id)
    check = (db.query(ComplianceCheck)
             .filter(ComplianceCheck.email_id == email.id)
             .order_by(ComplianceCheck.created_at.desc()).first())
    return EmailOut(
        id=email.id, lead_id=email.lead_id,
        lead_name=lead.full_name if lead else "", lead_email=lead.email if lead else "",
        subject_variants=email.subject_variants or [],
        selected_variant=email.selected_variant, body=email.body,
        groundedness=email.groundedness, grounding=email.grounding or [],
        tokens=email.tokens, cost_usd=email.cost_usd,
        edited_by_human=email.edited_by_human, status=email.status,
        compliance=({"verdict": check.verdict, "risk_score": check.risk_score,
                     "checks": check.checks} if check else None),
    )


@router.get("", response_model=list[EmailOut])
def list_emails(campaign_id: str | None = None, status: str | None = None,
                limit: int = Query(default=200, le=500),
                db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    stmt = select(GeneratedEmail).where(GeneratedEmail.tenant_id == user.tenant_id)
    if campaign_id:
        stmt = stmt.where(GeneratedEmail.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(GeneratedEmail.status == status)
    return [_out(db, e) for e in db.scalars(stmt.limit(limit)).all()]


@router.get("/{email_id}", response_model=EmailOut)
def get_email(email_id: str, db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    email = db.get(GeneratedEmail, email_id)
    if not email or email.tenant_id != user.tenant_id:
        raise NotFound("Email not found")
    return _out(db, email)


@router.patch("/{email_id}", response_model=EmailOut)
def edit_email(email_id: str, body: EmailEdit, db: Session = Depends(get_db),
               user: CurrentUser = Depends(require_permission("campaign:write"))):
    """A human edit is recorded, not hidden: edit rate is a quality metric."""
    email = db.get(GeneratedEmail, email_id)
    if not email or email.tenant_id != user.tenant_id:
        raise NotFound("Email not found")
    if body.body is not None and body.body != email.body:
        email.body = body.body
        email.edited_by_human = True
    if body.selected_variant is not None:
        email.selected_variant = body.selected_variant

    # Re-run compliance: an edited body has not been checked.
    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=new_workflow_id(), user_id=user.id,
                       user_name=user.name)
    get_agent("compliance").run(ctx, emails=[email])
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="email.edit", entity_type="generated_email",
                    entity_id=email.id, payload={"edited": email.edited_by_human}))
    db.commit()
    db.refresh(email)
    return _out(db, email)


@router.post("/approve")
def approve(body: ApprovalRequest, db: Session = Depends(get_db),
            user: CurrentUser = Depends(require_permission("email:approve"))):
    """Approval is attributable and blocked emails cannot be approved at all."""
    emails = list(db.scalars(select(GeneratedEmail).where(
        GeneratedEmail.id.in_(body.email_ids),
        GeneratedEmail.tenant_id == user.tenant_id)).all())
    if not emails:
        raise NotFound("No matching emails")

    blocked = []
    for email in emails:
        check = (db.query(ComplianceCheck)
                 .filter(ComplianceCheck.email_id == email.id)
                 .order_by(ComplianceCheck.created_at.desc()).first())
        if check and check.verdict == "BLOCK":
            blocked.append({"email_id": email.id,
                            "failed": [c["key"] for c in check.checks if not c["pass"]]})
    if blocked:
        raise PolicyViolation(
            "Compliance blocked one or more of these emails; they cannot be approved",
            {"blocked": blocked},
        )

    for email in emails:
        db.add(EmailApproval(
            tenant_id=user.tenant_id, email_id=email.id, decision=body.decision,
            approver_id=user.id, approver_name=user.name or user.email,
            justification=body.justification,
        ))
        email.status = "approved" if body.decision == "approved" else "rejected"
        db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id,
                        actor_name=user.name, action=f"email.{body.decision}",
                        entity_type="generated_email", entity_id=email.id,
                        payload={"justification": body.justification}))
    db.commit()
    return {"approved": len(emails), "decision": body.decision,
            "approver": user.name or user.email}


@router.post("/send")
def send(body: SendRequest, db: Session = Depends(get_db),
         user: CurrentUser = Depends(require_permission("email:approve"))):
    stmt = select(GeneratedEmail).where(
        GeneratedEmail.tenant_id == user.tenant_id,
        GeneratedEmail.status == "approved")
    if body.email_ids:
        stmt = stmt.where(GeneratedEmail.id.in_(body.email_ids))
    emails = list(db.scalars(stmt).all())
    if not emails:
        return {"sent": 0, "failed": 0, "skipped": 0, "results": [],
                "message": "No approved emails to send"}

    ctx = AgentContext(db=db, tenant_id=user.tenant_id,
                       workflow_id=new_workflow_id(), user_id=user.id,
                       user_name=user.name)
    result = get_agent("execution").run(ctx, emails=emails)
    db.add(AuditLog(tenant_id=user.tenant_id, actor_id=user.id, actor_name=user.name,
                    action="email.send", entity_type="campaign",
                    payload=result.output))
    db.commit()
    return result.output
