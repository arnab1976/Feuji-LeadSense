"""Sign-in.

``/auth/dev-token`` exists so the portal is usable the moment the repo is cloned.
Set AUTH_MODE=entra and it is disabled; the frontend then sends the Entra ID
token it obtained through MSAL and the API validates it against the JWKS.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user, get_db
from app.core.errors import NotFound, PermissionDenied
from app.core.security import PERMISSIONS, create_access_token
from app.models import Tenant, User
from app.schemas.auth import DevTokenRequest, MeResponse, TokenResponse

router = APIRouter()


@router.post("/dev-token", response_model=TokenResponse)
def dev_token(body: DevTokenRequest, db: Session = Depends(get_db)):
    """Issue a locally signed token for demos and local development."""
    if settings.auth_mode != "dev":
        raise PermissionDenied(
            "Dev tokens are disabled. Sign in through Microsoft Entra ID."
        )
    tenant = db.scalar(select(Tenant).where(Tenant.slug == body.tenant_slug))
    if not tenant:
        raise NotFound(f"Unknown tenant '{body.tenant_slug}'. Run `make seed` first.")

    user = db.scalar(
        select(User).where(User.tenant_id == tenant.id, User.email == body.email)
    )
    if not user:
        user = User(tenant_id=tenant.id, email=body.email, name=body.name,
                    role=body.role)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.role != body.role:
        user.role = body.role
        db.commit()

    claims = {"sub": user.id, "email": user.email, "name": user.name,
              "role": user.role, "tenant_id": tenant.id, "tenant_name": tenant.name}
    return TokenResponse(
        access_token=create_access_token(claims),
        expires_in_minutes=settings.jwt_expire_minutes,
        user={**claims, "permissions": sorted(PERMISSIONS.get(user.role, set()))},
    )


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(get_current_user)):
    return MeResponse(
        id=user.id, email=user.email, name=user.name, role=user.role,
        tenant_id=user.tenant_id, tenant_name=user.tenant_name,
        permissions=sorted(PERMISSIONS.get(user.role, set())),
    )
