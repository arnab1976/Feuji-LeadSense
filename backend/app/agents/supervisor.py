"""Agent 01 - Supervisor / Orchestration.

Owns the workflow state object, decides the next node, persists a checkpoint
after every step and pauses at human gates. It is the only agent that writes to
``workflow_states``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.models import WorkflowState


class SupervisorAgent(BaseAgent):
    key = "supervisor"
    name = "Supervisor / Orchestration"
    role = "Coordinates workflows, checkpoints, retries and human gates"
    inputs = "tenant_id, user_id, workflow type, entity IDs, workflow state"
    execution_strategy = (
        "Read persisted state; determine the next node; invoke the agent or "
        "service; validate output; persist the result; retry or pause; trigger "
        "human approval; resume from checkpoint."
    )
    outputs = "Workflow status, next action, state snapshot, trace identifiers"
    stack = "LangGraph, Python, FastAPI, Redis/PostgreSQL checkpoints, Langfuse"

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
        row.state = state
        row.current_node = node
        row.status = status
        row.paused_reason = paused_reason
        history = list(row.history or [])
        history.append({
            "node": node, "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
            "keys": sorted(patch.keys()),
        })
        row.history = history[-100:]
        ctx.db.flush()
        return row

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult:
        node = kwargs.get("node", "workflow.checkpoint")
        patch = kwargs.get("patch", {})
        status = kwargs.get("status", "running")
        paused_reason = kwargs.get("paused_reason", "")
        row = self.checkpoint(ctx, node, patch, status, paused_reason)
        return AgentResult(
            output={"workflow_id": row.workflow_id, "status": row.status,
                    "current_node": row.current_node,
                    "paused_reason": row.paused_reason, "state": row.state},
            decision=status.upper(), confidence=0.99,
            reason=f"checkpoint at {node}",
        )
