"""Workflow Orchestrator (pipeline control).

Owns the workflow state object, decides the next node, persists a checkpoint
after every step and pauses at human gates. This is orchestration infrastructure
— not a lead-processing agent. It is the only component that writes to
``workflow_states``.

Architecture:
  Agent 01 Ingestion → lead_ids
  → Orchestrator.checkpoint(ingestion / pipeline.start)
  → Extraction → Verification
  → [conflicts] checkpoint(PAUSED) → human review
  → [clear] Enrichment → Scoring
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import WorkflowState

# Ordered hand-off map used by ``next_action`` (matches LeadPipeline nodes).
_NEXT: dict[str, str] = {
    "ingestion": "pipeline.start",
    "pipeline.start": "extraction",
    "extraction": "verification",
    "verification": "enrichment",
    "enrichment": "scoring",
    "scoring": "pipeline.complete",
    "pipeline.resume": "enrichment",
}


class SupervisorAgent(BaseAgent):
    """Internal key stays ``supervisor`` for telemetry compatibility."""

    key = "supervisor"
    name = "Workflow Orchestrator"
    role = "Pipeline control — checkpoints, next-step routing, pause and resume"
    inputs = "tenant_id, user_id, workflow type, entity IDs, workflow state"
    execution_strategy = (
        "Read persisted state; determine the next node; invoke the agent or "
        "service; validate output; persist the result; retry or pause; trigger "
        "human approval; resume from checkpoint."
    )
    outputs = "Workflow status, next action, state snapshot, trace identifiers"
    stack = "LangGraph, Python, FastAPI, Redis/PostgreSQL checkpoints, Langfuse"
    kind = "orchestrator"

    # -- routing ---------------------------------------------------------
    @staticmethod
    def next_action(node: str, state: dict | None = None) -> str:
        """Decide what the pipeline should do after ``node``.

        Verification is a hard human gate: open conflicts force ``human_review``
        instead of enrichment.
        """
        state = state or {}
        if node == "verification" and int(state.get("open_conflicts") or 0) > 0:
            return "human_review"
        if node.endswith(".skipped"):
            base = node.split(".", 1)[0]
            return _NEXT.get(base, "pipeline.complete")
        return _NEXT.get(node, "pipeline.complete")

    # -- checkpointing ---------------------------------------------------
    @staticmethod
    def load(ctx: AgentContext) -> WorkflowState:
        row = (ctx.db.query(WorkflowState)
               .filter(WorkflowState.workflow_id == ctx.workflow_id).first())
        if not row:
            row = WorkflowState(
                tenant_id=ctx.tenant_id, workflow_id=ctx.workflow_id,
                state={"tenant_id": ctx.tenant_id, "user_id": ctx.user_id,
                       "trace_id": ctx.workflow_id},
                history=[],
            )
            ctx.db.add(row)
            ctx.db.flush()
        return row

    @staticmethod
    def checkpoint(ctx: AgentContext, node: str, patch: dict,
                   status: str = "running", paused_reason: str = "") -> WorkflowState:
        row = SupervisorAgent.load(ctx)
        state = dict(row.state or {})
        state.update(patch)
        next_action = SupervisorAgent.next_action(node, state)
        state["next_action"] = next_action
        state["awaiting_human_review"] = next_action == "human_review" or status == "paused"
        row.state = state
        row.current_node = node
        row.status = status
        row.paused_reason = paused_reason
        history = list(row.history or [])
        history.append({
            "node": node,
            "status": status,
            "next_action": next_action,
            "at": datetime.now(timezone.utc).isoformat(),
            "keys": sorted(patch.keys()),
        })
        row.history = history[-100:]
        ctx.db.flush()
        return row

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        node = kwargs.get("node", "workflow.checkpoint")
        patch = dict(kwargs.get("patch") or {})
        status = kwargs.get("status", "running")
        paused_reason = kwargs.get("paused_reason", "")
        row = self.checkpoint(ctx, node, patch, status, paused_reason)
        next_action = (row.state or {}).get("next_action", "")
        human = status == "paused" or next_action == "human_review"
        return AgentResult(
            output={
                "workflow_id": row.workflow_id,
                "status": row.status,
                "current_node": row.current_node,
                "next_action": next_action,
                "paused_reason": row.paused_reason,
                "awaiting_human_review": human,
                "state": row.state,
                "evidence": {
                    "node": node,
                    "next_action": next_action,
                    "status": status,
                },
            },
            decision="PAUSED" if human else status.upper(),
            confidence=0.99,
            reason=(
                paused_reason
                or f"checkpoint at {node}; next={next_action}"
            ),
            requires_human=human,
            pause_reason=paused_reason if human else "",
        )
