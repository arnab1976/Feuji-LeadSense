"""Agent instrumentation.

Every agent call writes an AgentExecution row and, where it made a judgement, an
AgentDecision row. This is what the Agent Monitor screen reads, and what makes
"show me why this lead was scored 82" answerable.

If Langfuse credentials are present the same span is mirrored there; the local
tables remain the source of truth so the demo works with no external service.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import AgentDecision, AgentExecution

log = get_logger("leadsense.telemetry")


def record_execution(
    db: Session, *, tenant_id: str, workflow_id: str, agent: str, node: str,
    latency_ms: int, status: str = "completed", tokens: int = 0,
    cost_usd: float = 0.0, model: str = "", error: str = "",
) -> AgentExecution:
    row = AgentExecution(
        tenant_id=tenant_id, workflow_id=workflow_id, agent=agent, node=node,
        latency_ms=latency_ms, status=status, tokens=tokens, cost_usd=cost_usd,
        model=model, error=error,
    )
    db.add(row)
    log.info("agent=%s node=%s status=%s %dms wf=%s", agent, node, status,
             latency_ms, workflow_id)
    _mirror_to_langfuse(agent, node, latency_ms, status, workflow_id)
    return row


def record_decision(
    db: Session, *, tenant_id: str, workflow_id: str, agent: str, decision: str,
    confidence: float, reason: str = "", entity_type: str = "", entity_id: str = "",
    evidence: dict | None = None, version: str = "", human_override: bool = False,
) -> AgentDecision:
    row = AgentDecision(
        tenant_id=tenant_id, workflow_id=workflow_id, agent=agent,
        entity_type=entity_type, entity_id=entity_id, decision=decision,
        confidence=confidence, reason=reason, evidence=evidence or {},
        model_or_rule_version=version, human_override=human_override,
    )
    db.add(row)
    return row


@contextmanager
def timed():
    """``with timed() as t: ...`` then ``t.ms``."""

    class _T:
        ms = 0

    t = _T()
    start = time.perf_counter()
    try:
        yield t
    finally:
        t.ms = int((time.perf_counter() - start) * 1000)


def _mirror_to_langfuse(agent, node, latency_ms, status, workflow_id) -> None:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return
    try:  # pragma: no cover - optional dependency
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        client.trace(id=workflow_id, name="leadsense.workflow").span(
            name=f"{agent}.{node}",
            metadata={"status": status, "latency_ms": latency_ms},
        )
    except Exception as exc:
        log.debug("langfuse mirror skipped: %s", exc)
