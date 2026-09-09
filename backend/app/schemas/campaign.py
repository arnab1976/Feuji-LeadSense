from typing import Any

from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str
    objective: str
    tone: str = "Consultative"
    segment_id: str
    knowledge_doc_ids: list[str] = Field(default_factory=list)


class CampaignOut(BaseModel):
    id: str
    name: str
    objective: str
    tone: str
    segment_id: str | None
    status: str
    strategy: dict[str, Any] = Field(default_factory=dict)
    email_count: int = 0


class GenerateEmailsRequest(BaseModel):
    lead_ids: list[str] = Field(default_factory=list)
    regenerate: bool = False


class EmailOut(BaseModel):
    id: str
    lead_id: str
    lead_name: str = ""
    lead_email: str = ""
    subject_variants: list[str]
    selected_variant: int
    body: str
    groundedness: float
    grounding: list[dict[str, Any]] = Field(default_factory=list)
    tokens: int
    cost_usd: float
    edited_by_human: bool
    status: str
    compliance: dict[str, Any] | None = None


class EmailEdit(BaseModel):
    body: str | None = None
    selected_variant: int | None = None


class ApprovalRequest(BaseModel):
    email_ids: list[str]
    decision: str = "approved"
    justification: str = ""


class SendRequest(BaseModel):
    email_ids: list[str] = Field(default_factory=list)
    schedule_at: str | None = None


class ReplyIn(BaseModel):
    email_id: str | None = None
    lead_id: str
    body: str


class ReplyOut(BaseModel):
    id: str
    lead_id: str
    body: str
    intent: str
    confidence: float
    score_delta: int
    next_action: str
    requires_human: bool
    action_status: str
    crm_payload: dict[str, Any] = Field(default_factory=dict)
