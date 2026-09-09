"""Campaign, generated email, compliance, approval, delivery and reply."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Campaign(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(60), default="Consultative")
    segment_id: Mapped[str | None] = mapped_column(ForeignKey("segments.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    knowledge_doc_ids: Mapped[list] = mapped_column(JSON, default=list)
    workflow_id: Mapped[str] = mapped_column(String(60), default="")


class GeneratedEmail(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "generated_emails"

    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    step: Mapped[int] = mapped_column(Integer, default=1)
    subject_variants: Mapped[list] = mapped_column(JSON, default=list)
    selected_variant: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(Text, default="")
    grounding: Mapped[list] = mapped_column(JSON, default=list)
    groundedness: Mapped[float] = mapped_column(Float, default=0.0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str] = mapped_column(String(80), default="")
    edited_by_human: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)


class ComplianceCheck(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "compliance_checks"

    email_id: Mapped[str] = mapped_column(ForeignKey("generated_emails.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(30), default="NEEDS_REVIEW", index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    checks: Mapped[list] = mapped_column(JSON, default=list)


class EmailApproval(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "email_approvals"

    email_id: Mapped[str] = mapped_column(ForeignKey("generated_emails.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20), default="approved")
    approver_id: Mapped[str] = mapped_column(String(36), default="")
    approver_name: Mapped[str] = mapped_column(String(200), default="")
    justification: Mapped[str] = mapped_column(Text, default="")


class EmailSendJob(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "email_send_jobs"

    email_id: Mapped[str] = mapped_column(ForeignKey("generated_emails.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30), default="console")
    provider_message_id: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class EmailEvent(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "email_events"

    email_id: Mapped[str | None] = mapped_column(ForeignKey("generated_emails.id"), index=True)
    provider_message_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Reply(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "replies"

    email_id: Mapped[str | None] = mapped_column(ForeignKey("generated_emails.id"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(40), default="", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    score_delta: Mapped[int] = mapped_column(Integer, default=0)
    next_action: Mapped[str] = mapped_column(Text, default="")
    requires_human: Mapped[bool] = mapped_column(Boolean, default=False)
    action_status: Mapped[str] = mapped_column(String(30), default="proposed")
    crm_payload: Mapped[dict] = mapped_column(JSON, default=dict)
