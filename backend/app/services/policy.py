"""Source policy, lawful basis, suppression and sending policy.

These checks live in one module because they are the controls an enterprise buyer
audits. Everything that can block an outbound message is here.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PolicyConfig, SourceConnection, SuppressionEntry

DEFAULT_SENDING_POLICY = {
    "max_sends_per_minute": 14,
    "max_sends_per_day": 500,
    "max_contacts_per_lead_per_30d": 1,
    "require_unsubscribe_link": True,
}


def get_policy(db: Session, tenant_id: str) -> PolicyConfig:
    policy = db.scalar(select(PolicyConfig).where(PolicyConfig.tenant_id == tenant_id))
    if not policy:
        policy = PolicyConfig(
            tenant_id=tenant_id, sending_policy=dict(DEFAULT_SENDING_POLICY),
            source_policy={}, scoring_weights={},
        )
        db.add(policy)
        db.flush()
    return policy


def is_suppressed(db: Session, tenant_id: str, email: str) -> bool:
    if not email:
        return False
    return bool(db.scalar(
        select(SuppressionEntry).where(
            SuppressionEntry.tenant_id == tenant_id,
            SuppressionEntry.email == email.lower(),
        )
    ))


def suppress(db: Session, tenant_id: str, email: str, reason: str,
             source: str = "system") -> SuppressionEntry:
    if is_suppressed(db, tenant_id, email):
        return db.scalar(select(SuppressionEntry).where(
            SuppressionEntry.tenant_id == tenant_id,
            SuppressionEntry.email == email.lower()))
    entry = SuppressionEntry(tenant_id=tenant_id, email=email.lower(),
                             reason=reason, source=source)
    db.add(entry)
    db.flush()
    return entry


def source_allowed(db: Session, tenant_id: str, connection_id: str | None) -> tuple[bool, str]:
    """Extraction and outreach are permitted only for enabled, allowed sources."""
    if not connection_id:
        return True, "no source connection recorded"
    conn = db.get(SourceConnection, connection_id)
    if not conn:
        return True, "source connection not found"
    if not conn.is_enabled:
        return False, f"source '{conn.name}' is disabled for this tenant"
    if not conn.policy_allowed:
        return False, f"source '{conn.name}' is not permitted by tenant source policy"
    return True, f"source '{conn.name}' is permitted"


def lawful_basis_recorded(db: Session, connection_id: str | None) -> tuple[bool, str]:
    if not connection_id:
        return True, "manual upload - lawful basis asserted by the uploading tenant"
    conn = db.get(SourceConnection, connection_id)
    if not conn:
        return True, "source connection not found"
    if conn.lawful_basis in ("", "unknown", "none"):
        return False, f"no lawful basis recorded for '{conn.name}'"
    return True, f"lawful basis '{conn.lawful_basis}' recorded for '{conn.name}'"
