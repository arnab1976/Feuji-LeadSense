"""FastAPI dependencies: database session, current user, tenant scope, RBAC."""
from dataclasses import dataclass
from typing import Iterator

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import PermissionDenied
from app.core.security import decode_token, has_permission
from app.db.session import SessionLocal


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass
class CurrentUser:
    id: str
    email: str
    name: str
    role: str
    tenant_id: str
    tenant_name: str = ""

    def require(self, permission: str) -> None:
        if not has_permission(self.role, permission):
            raise PermissionDenied(
                f"Role '{self.role}' lacks permission '{permission}'"
            )


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    if not authorization.lower().startswith("bearer "):
        raise PermissionDenied("Missing bearer token")
    claims = decode_token(authorization.split(" ", 1)[1])
    return CurrentUser(
        id=claims.get("sub", ""),
        email=claims.get("email", claims.get("preferred_username", "")),
        name=claims.get("name", ""),
        role=claims.get("role", "read_only"),
        tenant_id=claims.get("tenant_id", ""),
        tenant_name=claims.get("tenant_name", ""),
    )


def require_permission(permission: str):
    """Router dependency factory: ``Depends(require_permission("lead:write"))``."""

    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user.require(permission)
        return user

    return _checker
