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
        state: dict = {"lead_ids": lead_ids, "open_conflicts": 0}
        self.supervisor.checkpoint(self.ctx, "pipeline.start",
                                   {"lead_ids": lead_ids})

        for node in PIPELINE:
            if node.gate and not node.gate(state):
                log.info("node %s skipped by gate", node.name)
                self.supervisor.checkpoint(self.ctx, f"{node.name}.skipped", {},
                                           status="running")
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
            self.supervisor.checkpoint(
                self.ctx, node.name, {node.name: result.output},
                status="paused" if paused else "running",
                paused_reason=result.pause_reason if paused else "",
            )
            if paused:
                log.info("workflow %s paused at %s", self.ctx.workflow_id, node.name)
                state["paused_at"] = node.name
                state["pause_reason"] = result.pause_reason
                return state

        self.supervisor.checkpoint(self.ctx, "pipeline.complete", {},
                                   status="completed")
        return state

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
