"""Agent contract.

Every agent is a small class with one job, a declared input and output, and an
execution strategy written down in the docstring. That is deliberate: the
architecture document describes 13 agent responsibilities, and this module is
where those descriptions become executable rather than aspirational.

An agent never commits the session. The orchestrator owns the transaction so a
failed node can be retried without half-written state.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services.telemetry import record_decision, record_execution, timed

log = get_logger("leadsense.agents")


@dataclass
class AgentContext:
    """Everything an agent is allowed to know about its run."""

    db: Session
    tenant_id: str
    workflow_id: str
    user_id: str = ""
    user_name: str = ""
    config: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    output: dict = field(default_factory=dict)
    decision: str = "COMPLETED"
    confidence: float = 1.0
    reason: str = ""
    tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    latency_ms: int = 0
    requires_human: bool = False
    pause_reason: str = ""


class BaseAgent(ABC):
    key: str = ""
    name: str = ""
    role: str = ""
    inputs: str = ""
    execution_strategy: str = ""
    outputs: str = ""
    stack: str = ""
    version: str = "v1"

    @abstractmethod
    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        """Do the work. Raise to signal a retryable failure."""

    # -- instrumentation wrapper ----------------------------------------
    def run(self, ctx: AgentContext, **kwargs) -> AgentResult:
        with timed() as t:
            try:
                result = self.execute(ctx, **kwargs)
                status = "paused" if result.requires_human else "completed"
                error = ""
            except Exception as exc:  # noqa: BLE001 - recorded then re-raised
                record_execution(
                    ctx.db, tenant_id=ctx.tenant_id, workflow_id=ctx.workflow_id,
                    agent=self.key, node=f"{self.key}.execute",
                    latency_ms=0, status="failed", error=str(exc),
                )
                log.exception("agent %s failed", self.key)
                raise
        result.latency_ms = t.ms
        record_execution(
            ctx.db, tenant_id=ctx.tenant_id, workflow_id=ctx.workflow_id,
            agent=self.key, node=f"{self.key}.execute", latency_ms=t.ms,
            status=status, tokens=result.tokens, cost_usd=result.cost_usd,
            model=result.model, error=error,
        )
        record_decision(
            ctx.db, tenant_id=ctx.tenant_id, workflow_id=ctx.workflow_id,
            agent=self.key, decision=result.decision, confidence=result.confidence,
            reason=result.reason, evidence=result.output.get("evidence", {}),
            version=f"{self.key}-{self.version}",
        )
        return result

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "key": cls.key, "name": cls.name, "role": cls.role,
            "inputs": cls.inputs, "execution_strategy": cls.execution_strategy,
            "outputs": cls.outputs, "stack": cls.stack, "version": cls.version,
        }
