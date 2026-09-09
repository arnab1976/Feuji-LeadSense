"""Tenancy, identity, source connections, policy and audit."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Tenant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    entra_tenant_id: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(30), default="active")
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)


class User(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(40), default="read_only")
    external_id: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SourceConnection(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """A configured instance of a source connector for one tenant.

    ``connector_key`` maps to a class in ``app.connectors``. ``config_json`` holds
    connector-specific settings; secrets should be stored as references to AWS
    Secrets Manager in production rather than raw values.
    """

    __tablename__ = "source_connections"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    connector_key: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="configured")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    policy_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    lawful_basis: Mapped[str] = mapped_column(String(60), default="legitimate_interest")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_cursor: Mapped[str] = mapped_column(String(255), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")


class PolicyConfig(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Tenant-level source, sending and scoring policy."""

    __tablename__ = "policy_configs"

    source_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    sending_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    scoring_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    campaign_threshold: Mapped[int] = mapped_column(default=70)
    require_approval_before_send: Mapped[bool] = mapped_column(Boolean, default=True)


class SuppressionEntry(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "suppression_entries"

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), default="unsubscribe")
    source: Mapped[str] = mapped_column(String(80), default="manual")


class AuditLog(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    actor_id: Mapped[str] = mapped_column(String(36), default="")
    actor_name: Mapped[str] = mapped_column(String(200), default="")
    action: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
