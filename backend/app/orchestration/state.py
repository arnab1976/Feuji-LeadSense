"""The workflow state object passed between nodes.

This mirrors the state shape in the architecture document. Keeping it as a
TypedDict means LangGraph can use it directly as its StateGraph schema.
"""
from __future__ import annotations

from typing import Any, TypedDict


class LeadSenseState(TypedDict, total=False):
    tenant_id: str
    user_id: str
    trace_id: str
    lead_ids: list[str]
    campaign_id: str
    segment_id: str
    job_id: str
    profile: dict[str, Any]
    verification: dict[str, Any]
    enrichment: dict[str, Any]
    score: dict[str, Any]
    segment: dict[str, Any]
    campaign_strategy: dict[str, Any]
    generated_email: dict[str, Any]
    compliance: dict[str, Any]
    approval_status: str
    send_status: dict[str, Any]
    engagement: dict[str, Any]
    reply_intent: str
    next_action: str


def new_workflow_id(prefix: str = "WF") -> str:
    from datetime import datetime, timezone
    import random

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{random.randint(10000, 99999)}"
