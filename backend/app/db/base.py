"""Declarative base plus shared column mixins."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow,
        onupdate=utcnow,
    )


class UUIDMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class TenantMixin:
    """Every tenant-scoped record carries tenant_id.

    The demo uses a shared database with tenant_id on every row. Production can
    switch to PostgreSQL Row-Level Security or schema-per-tenant without any
    change to the models below.
    """

    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
