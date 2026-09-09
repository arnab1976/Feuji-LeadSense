from typing import Any

from pydantic import BaseModel, Field


class LeadOut(BaseModel):
    id: str
    full_name: str
    email: str
    title: str
    company_name: str
    location: str
    connector_key: str
    status: str
    score: int | None = None
    band: str | None = None
    persona: str | None = None
    seniority: str | None = None
    verification_status: str | None = None


class LeadDetail(LeadOut):
    profile_url: str = ""
    industry: str = ""
    employee_count: int = 0
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    extraction: dict[str, Any] | None = None
    verifications: list[dict[str, Any]] = Field(default_factory=list)
    enrichment: dict[str, Any] | None = None
    score_detail: dict[str, Any] | None = None


class MappingPreview(BaseModel):
    headers: list[str]
    mapping: dict[str, str]
    unmapped_headers: list[str]
    sample_rows: list[dict[str, Any]]
    rows_detected: int


class IngestResult(BaseModel):
    job_id: str
    rows_read: int
    rows_valid: int
    rows_invalid: int
    rows_duplicate: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    lead_ids: list[str] = Field(default_factory=list)


class ConflictResolution(BaseModel):
    verification_id: str
    resolution: str = Field(description="uploaded | extracted | custom")
    custom_value: str = ""


class BulkResolution(BaseModel):
    lead_ids: list[str] = Field(default_factory=list)
    resolution: str = "extracted"


class ScoreRequest(BaseModel):
    lead_ids: list[str] = Field(default_factory=list)
    weights: dict[str, int] | None = None


class SegmentCreate(BaseModel):
    name: str
    description: str = ""
    method: str = "rules"
    min_score: int = 70
    group_by: str = "persona"
    min_size: int = 2
    industries: list[str] = Field(default_factory=list)
