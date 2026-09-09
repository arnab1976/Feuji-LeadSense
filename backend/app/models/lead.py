"""Lead lifecycle: ingestion, extraction, verification, enrichment, scoring."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class IngestJob(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "ingest_jobs"

    source_connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_connections.id"), index=True
    )
    connector_key: Mapped[str] = mapped_column(String(60), default="manual_upload")
    filename: Mapped[str] = mapped_column(String(255), default="")
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)


class Company(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), default="")
    domain: Mapped[str] = mapped_column(String(200), default="")
    industry: Mapped[str] = mapped_column(String(120), default="")
    employee_count: Mapped[int] = mapped_column(Integer, default=0)
    tech_stack: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str] = mapped_column(String(80), default="")


class Lead(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """The uploaded record. Extracted values live in LeadExtraction so the two
    versions can be compared rather than overwritten."""

    __tablename__ = "leads"

    ingest_job_id: Mapped[str | None] = mapped_column(ForeignKey("ingest_jobs.id"), index=True)
    source_connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_connections.id"), index=True
    )
    connector_key: Mapped[str] = mapped_column(String(60), default="manual_upload")
    external_id: Mapped[str] = mapped_column(String(120), default="", index=True)

    full_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(255), default="", index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    company_name: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    profile_url: Mapped[str] = mapped_column(String(500), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")

    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(120), default="", index=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(36))

    status: Mapped[str] = mapped_column(String(40), default="ingested", index=True)
    workflow_id: Mapped[str] = mapped_column(String(60), default="")

    extractions: Mapped[list["LeadExtraction"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    verifications: Mapped[list["LeadVerification"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class LeadExtraction(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "lead_extractions"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    source: Mapped[str] = mapped_column(String(80), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(40), default="extracted")
    error: Mapped[str] = mapped_column(Text, default="")

    lead: Mapped["Lead"] = relationship(back_populates="extractions")


class LeadVerification(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """One row per reconciled field: MATCH / MISMATCH / NEEDS_REVIEW."""

    __tablename__ = "lead_verifications"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    uploaded_value: Mapped[str] = mapped_column(Text, default="")
    extracted_value: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(String(40), default="rule")
    resolved_value: Mapped[str] = mapped_column(Text, default="")
    resolved_source: Mapped[str] = mapped_column(String(20), default="")
    resolved_by: Mapped[str] = mapped_column(String(200), default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lead: Mapped["Lead"] = relationship(back_populates="verifications")


class LeadEnrichment(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "lead_enrichments"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True, unique=True)
    normalized_title: Mapped[str] = mapped_column(String(200), default="")
    seniority: Mapped[str] = mapped_column(String(60), default="")
    seniority_rank: Mapped[int] = mapped_column(Integer, default=0)
    function: Mapped[str] = mapped_column(String(80), default="")
    persona: Mapped[str] = mapped_column(String(80), default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    industry: Mapped[str] = mapped_column(String(120), default="")
    employee_count: Mapped[int] = mapped_column(Integer, default=0)
    tech_stack: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class LeadScore(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "lead_scores"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    band: Mapped[str] = mapped_column(String(20), default="LOW", index=True)
    factors: Mapped[dict] = mapped_column(JSON, default=dict)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(40), default="score-rules-v1")


class Segment(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "segments"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    method: Mapped[str] = mapped_column(String(40), default="rules")
    size: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class SegmentMember(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "segment_members"

    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
