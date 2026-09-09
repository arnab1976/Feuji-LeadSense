"""Tenant, policy and suppression administration."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.models import SuppressionEntry, Tenant
from app.services import policy as policy_service

router = APIRouter()


@router.get("")
def list_tenants(db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(select(Tenant)).all()
    return [{"id": t.id, "name": t.name, "slug": t.slug, "status": t.status}
            for t in rows]


@router.get("/policy")
def get_policy(db: Session = Depends(get_db),
               user: CurrentUser = Depends(get_current_user)):
    policy = policy_service.get_policy(db, user.tenant_id)
    db.commit()
    return {
        "source_policy": policy.source_policy,
        "sending_policy": policy.sending_policy,
        "scoring_weights": policy.scoring_weights,
        "campaign_threshold": policy.campaign_threshold,
        "require_approval_before_send": policy.require_approval_before_send,
    }


@router.put("/policy")
def update_policy(body: dict, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_permission("policy:manage"))):
    policy = policy_service.get_policy(db, user.tenant_id)
    for field in ("source_policy", "sending_policy", "scoring_weights",
                  "campaign_threshold", "require_approval_before_send"):
        if field in body:
            setattr(policy, field, body[field])
    db.commit()
    return {"message": "Policy updated"}


@router.get("/suppression")
def list_suppression(db: Session = Depends(get_db),
                     user: CurrentUser = Depends(get_current_user)):
    rows = db.scalars(
        select(SuppressionEntry).where(SuppressionEntry.tenant_id == user.tenant_id)
    ).all()
    return [{"id": r.id, "email": r.email, "reason": r.reason, "source": r.source,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.post("/suppression")
def add_suppression(body: dict, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_permission("policy:manage"))):
    entry = policy_service.suppress(db, user.tenant_id, body["email"],
                                    body.get("reason", "manual"), "manual")
    db.commit()
    return {"id": entry.id, "email": entry.email}
