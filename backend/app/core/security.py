"""Identity and access.

Two modes:

* ``dev``   - the API issues and validates its own HS256 tokens. Nothing external
              is required, which keeps the demo runnable offline.
* ``entra`` - tokens are validated against Microsoft Entra ID's JWKS endpoint.
              Set ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_AUDIENCE.

Both paths end at the same place: a resolved tenant, user and role set that every
router depends on before any business workflow runs.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.core.errors import PermissionDenied

ROLES = [
    "platform_admin",
    "tenant_admin",
    "sales_manager",
    "campaign_manager",
    "sales_executive",
    "reviewer",
    "analyst",
    "read_only",
]

# Permission matrix. Extend here rather than sprinkling role checks in routers.
PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {"*"},
    "tenant_admin": {
        "tenant:manage", "source:manage", "lead:read", "lead:write",
        "campaign:read", "campaign:write", "email:approve", "policy:manage",
        "analytics:read", "audit:read",
    },
    "sales_manager": {
        "lead:read", "lead:write", "campaign:read", "campaign:write",
        "email:approve", "analytics:read",
    },
    "campaign_manager": {
        "lead:read", "campaign:read", "campaign:write", "analytics:read",
    },
    "sales_executive": {"lead:read", "campaign:read", "analytics:read"},
    "reviewer": {"lead:read", "lead:write", "email:approve", "campaign:read"},
    "analyst": {"lead:read", "campaign:read", "analytics:read"},
    "read_only": {"lead:read", "campaign:read"},
}

_jwks_cache: dict[str, Any] = {}


def create_access_token(claims: dict[str, Any], minutes: int | None = None) -> str:
    payload = dict(claims)
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=minutes or settings.jwt_expire_minutes
    )
    payload.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _entra_jwks() -> dict[str, Any]:
    if _jwks_cache:
        return _jwks_cache
    url = (
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        "/discovery/v2.0/keys"
    )
    with httpx.Client(timeout=10) as client:
        _jwks_cache.update(client.get(url).json())
    return _jwks_cache


def decode_token(token: str) -> dict[str, Any]:
    """Validate a bearer token and return its claims."""
    if settings.auth_mode == "dev":
        try:
            return jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
        except JWTError as exc:  # pragma: no cover - defensive
            raise PermissionDenied(f"Invalid token: {exc}") from exc

    # Entra ID / OIDC
    try:
        jwks = _entra_jwks()
        return jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.entra_audience or settings.entra_client_id,
            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        )
    except JWTError as exc:
        raise PermissionDenied(f"Invalid Entra token: {exc}") from exc


def has_permission(role: str, permission: str) -> bool:
    granted = PERMISSIONS.get(role, set())
    return "*" in granted or permission in granted
