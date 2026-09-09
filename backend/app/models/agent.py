"""Agent execution, decision and workflow-state persistence.

These three tables are what make the Agent Monitor screen possible: every node
run, every decision and every checkpoint is queryable.
"""
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class AgentExecution(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "agent_executions"

    workflow_id: Mapped[str] = mapped_column(String(60), index=True)
    agent: Mapped[str] = mapped_column(String(60), index=True)
    node: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(30), default="completed")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str] = mapped_column(String(80), default="")
    error: Mapped[str] = mapped_column(Text, default="")


class AgentDecision(Base, UUIDMixin, TenantMixin, TimestampMixin):
    __tablename__ = "agent_decisions"

    workflow_id: Mapped[str] = mapped_column(String(60), index=True)
    agent: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    decision: Mapped[str] = mapped_column(String(60), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    model_or_rule_version: Mapped[str] = mapped_column(String(60), default="")
    human_override: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkflowState(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """LangGraph checkpoint. One row per workflow, updated after every node."""

    __tablename__ = "workflow_states"

    workflow_id: Mapped[str] = mapped_column(String(60), index=True, unique=True)
    workflow_type: Mapped[str] = mapped_column(String(60), default="lead_to_action")
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    current_node: Mapped[str] = mapped_column(String(80), default="")
    paused_reason: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
