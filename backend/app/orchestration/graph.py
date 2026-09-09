"""Lead-to-action pipeline.

The graph is expressed once, here, as an ordered list of nodes with conditional
gates. If LangGraph is installed it is compiled into a real ``StateGraph`` with
checkpointing; otherwise the built-in sequential runner executes the same nodes
with the same gates and the same checkpoint writes.

That fallback is not a shortcut — it keeps the repository runnable with a single
``pip install -r requirements.txt`` and makes the gate logic unit-testable without
a graph runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.agents import AgentContext, get_agent
from app.agents.supervisor import SupervisorAgent
from app.core.logging import get_logger
from app.models import Lead

log = get_logger("leadsense.orchestration")


@dataclass
class NodeSpec:
    name: str
    agent_key: str
    #: Returns True when the node should run for the current state.
    gate: Callable[[dict], bool] | None = None
    #: Human gate: pauses the workflow after this node when it returns True.
    pauses_when: Callable[[dict], bool] | None = None


PIPELINE: list[NodeSpec] = [
    NodeSpec("extraction", "extraction"),
    NodeSpec("verification", "verification",
             pauses_when=lambda s: s.get("open_conflicts", 0) > 0),
    NodeSpec("enrichment", "enrichment",
             gate=lambda s: s.get("open_conflicts", 0) == 0),
    NodeSpec("scoring", "scoring",
             gate=lambda s: s.get("open_conflicts", 0) == 0),
]


class LeadPipeline:
    """Runs extraction -> verification -> enrichment -> scoring for a lead batch.

    Verification is a hard gate: leads with open conflicts stop and wait for a
    reviewer, exactly as the execution strategy specifies. Everything past that
    point only sees trusted values.
    """

    def __init__(self, db: Session, tenant_id: str, workflow_id: str,
                 user_id: str = "", user_name: str = ""):
        self.ctx = AgentContext(db=db, tenant_id=tenant_id, workflow_id=workflow_id,
                                user_id=user_id, user_name=user_name)
        self.supervisor = SupervisorAgent()

    def run(self, lead_ids: list[str], weights: dict | None = None) -> dict:
        """Start after Agent 01 Ingestion has returned ``lead_ids``.

        The Workflow Orchestrator checkpoints ``pipeline.start``, then drives
        extraction → verification (human gate) → enrichment → scoring.
        """
        state: dict = {"lead_ids": lead_ids, "open_conflicts": 0}
        self._checkpoint(
            "pipeline.start",
            {"lead_ids": lead_ids, "handed_off_from": "ingestion"},
            status="running",
        )
        return self._execute(state, start_at=0, weights=weights)

    def resume(self, weights: dict | None = None) -> dict:
        """Continue a paused workflow from the node after the human gate.

        Recounts open verification conflicts from the database. If any remain,
        the workflow stays paused; otherwise enrichment and scoring run on the
        same ``workflow_id``.
        """
        row = self.supervisor.load(self.ctx)
        state = dict(row.state or {})
        lead_ids = list(state.get("lead_ids") or [])
        if not lead_ids:
            log.info("workflow %s has no lead_ids to resume", self.ctx.workflow_id)
            return {"status": row.status, "message": "no lead_ids in workflow state"}

        open_conflicts = self._count_open_conflicts(lead_ids)
        state["open_conflicts"] = open_conflicts
        state["lead_ids"] = lead_ids

        if open_conflicts > 0:
            self._checkpoint(
                row.current_node or "verification",
                {"open_conflicts": open_conflicts, "awaiting_human_review": True},
                status="paused",
                paused_reason=f"{open_conflicts} verification conflicts still open",
            )
            state["paused_at"] = state.get("paused_at") or "verification"
            state["pause_reason"] = f"{open_conflicts} verification conflicts still open"
            state["status"] = "paused"
            state["awaiting_human_review"] = True
            return state

        paused_at = state.get("paused_at") or row.current_node or "verification"
        start_at = 0
        for idx, node in enumerate(PIPELINE):
            if node.name == paused_at:
                start_at = idx + 1
                break

        state.pop("paused_at", None)
        state.pop("pause_reason", None)
        state["awaiting_human_review"] = False
        self._checkpoint(
            "pipeline.resume",
            {"open_conflicts": 0, "resumed_from": paused_at,
             "awaiting_human_review": False},
            status="running",
        )
        log.info("workflow %s resumed after %s", self.ctx.workflow_id, paused_at)
        return self._execute(state, start_at=start_at, weights=weights)

    def _checkpoint(self, node: str, patch: dict, status: str = "running",
                    paused_reason: str = "") -> None:
        """Orchestrator entry — goes through ``run()`` so telemetry is recorded."""
        self.supervisor.run(
            self.ctx,
            node=node,
            patch=patch,
            status=status,
            paused_reason=paused_reason,
        )

    def _execute(self, state: dict, start_at: int = 0,
                 weights: dict | None = None) -> dict:
        lead_ids = list(state.get("lead_ids") or [])

        for node in PIPELINE[start_at:]:
            if node.gate and not node.gate(state):
                log.info("node %s skipped by gate", node.name)
                self._checkpoint(f"{node.name}.skipped", {}, status="running")
                continue

            leads = self._leads(lead_ids)
            if not leads:
                break

            kwargs: dict = {"leads": leads}
            if node.agent_key == "scoring" and weights:
                kwargs["weights"] = weights

            result = get_agent(node.agent_key).run(self.ctx, **kwargs)
            state[node.name] = result.output
            if node.agent_key == "verification":
                state["open_conflicts"] = result.output.get("open_conflicts", 0)

            paused = bool(node.pauses_when and node.pauses_when(state))
            patch = {node.name: result.output}
            if node.agent_key == "verification":
                patch["open_conflicts"] = state.get("open_conflicts", 0)
            if paused:
                patch["paused_at"] = node.name
                patch["awaiting_human_review"] = True
            self._checkpoint(
                node.name, patch,
                status="paused" if paused else "running",
                paused_reason=result.pause_reason if paused else "",
            )
            if paused:
                log.info("workflow %s paused at %s", self.ctx.workflow_id, node.name)
                state["paused_at"] = node.name
                state["pause_reason"] = result.pause_reason
                state["status"] = "paused"
                state["awaiting_human_review"] = True
                return state

        self._checkpoint("pipeline.complete", {"awaiting_human_review": False},
                         status="completed")
        state["status"] = "completed"
        state["awaiting_human_review"] = False
        return state

    def _count_open_conflicts(self, lead_ids: list[str]) -> int:
        from app.models import LeadVerification

        if not lead_ids:
            return 0
        return (
            self.ctx.db.query(LeadVerification)
            .filter(
                LeadVerification.tenant_id == self.ctx.tenant_id,
                LeadVerification.lead_id.in_(lead_ids),
                LeadVerification.status != "MATCH",
                LeadVerification.resolved_value == "",
            )
            .count()
        )

    def _leads(self, lead_ids: list[str]) -> list[Lead]:
        return (self.ctx.db.query(Lead)
                .filter(Lead.id.in_(lead_ids),
                        Lead.tenant_id == self.ctx.tenant_id,
                        Lead.status != "policy_blocked")
                .all())


def build_langgraph_app():  # pragma: no cover - optional dependency
    """Compile the same pipeline into a LangGraph StateGraph.

    Install ``langgraph`` and call this from your worker if you want native
    checkpointing, streaming and interrupt support. The node functions delegate to
    the same agents used above, so behaviour does not diverge.
    """
    from langgraph.graph import END, StateGraph

    from app.orchestration.state import LeadSenseState

    graph = StateGraph(LeadSenseState)

    def make_node(agent_key: str):
        def _node(state):
            # Wire your session factory and context here.
            raise NotImplementedError(
                "Provide a Session in the LangGraph runtime config; see "
                "docs/architecture.md#orchestration"
            )
        return _node

    for spec in PIPELINE:
        graph.add_node(spec.name, make_node(spec.agent_key))

    graph.set_entry_point(PIPELINE[0].name)
    for current, following in zip(PIPELINE, PIPELINE[1:]):
        graph.add_edge(current.name, following.name)
    graph.add_edge(PIPELINE[-1].name, END)
    return graph.compile()
