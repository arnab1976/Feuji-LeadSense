"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AgentSpec } from "@/lib/types";
import { RequireSession, Badge, Notice, Empty } from "@/components/Ui";

export default function AgentsPage() {
  return (
    <RequireSession>
      <Agents />
    </RequireSession>
  );
}

function Agents() {
  const [catalog, setCatalog] = useState<AgentSpec[]>([]);
  const [executions, setExecutions] = useState<any[]>([]);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<AgentSpec[]>("/agents/catalog").then(setCatalog).catch((e) => setError(e.message));
    api.get<any[]>("/agents/executions").then(setExecutions).catch(() => {});
    api.get<any[]>("/agents/decisions").then(setDecisions).catch(() => {});
    api.get<any[]>("/agents/workflows").then(setWorkflows).catch(() => {});
  }, []);

  return (
    <>
      <div className="page-head">
        <h1>Agents</h1>
        <p>
          Thirteen agents, each with a declared role, execution strategy and output.
          Every run and every decision is recorded, which is what makes an agent
          answerable after the fact.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>

      <div className="card">
        <h2>Agent catalog</h2>
        <div className="grid cols-3">
          {catalog.map((agent) => (
            <div
              key={agent.key}
              className="stat"
              style={{ cursor: "pointer" }}
              onClick={() => setOpen(open === agent.key ? null : agent.key)}
            >
              <div className="label">Agent {String(agent.number).padStart(2, "0")}</div>
              <div style={{ fontWeight: 700, marginTop: 2 }}>{agent.name}</div>
              <div className="small muted" style={{ marginTop: 4 }}>
                {agent.role}
              </div>
              {open === agent.key && (
                <div className="small" style={{ marginTop: 10 }}>
                  <p>
                    <strong>Inputs:</strong> {agent.inputs}
                  </p>
                  <p>
                    <strong>Strategy:</strong> {agent.execution_strategy}
                  </p>
                  <p>
                    <strong>Outputs:</strong> {agent.outputs}
                  </p>
                  <p className="muted mono">{agent.stack}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Workflows</h2>
        {workflows.length === 0 ? (
          <Empty>No workflow runs yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Workflow</th>
                  <th>Status</th>
                  <th>Current node</th>
                  <th>Paused reason</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((wf) => (
                  <tr key={wf.workflow_id}>
                    <td className="mono small">{wf.workflow_id}</td>
                    <td>
                      <Badge kind={wf.status === "paused" ? "warn" : wf.status === "completed" ? "ok" : "neutral"}>
                        {wf.status}
                      </Badge>
                    </td>
                    <td className="small">{wf.current_node}</td>
                    <td className="small muted">{wf.paused_reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Recent executions</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Latency</th>
                  <th>Tokens</th>
                </tr>
              </thead>
              <tbody>
                {executions.slice(0, 18).map((row) => (
                  <tr key={row.id}>
                    <td className="mono small">{row.agent}</td>
                    <td>
                      <Badge kind={row.status === "failed" ? "bad" : row.status === "paused" ? "warn" : "ok"}>
                        {row.status}
                      </Badge>
                    </td>
                    <td className="small">{row.latency_ms} ms</td>
                    <td className="small">{row.tokens || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h2>Decision trace</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Decision</th>
                  <th>Confidence</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {decisions.slice(0, 18).map((row) => (
                  <tr key={row.id}>
                    <td className="mono small">{row.agent}</td>
                    <td>
                      <Badge kind={row.human_override ? "agent" : "neutral"}>
                        {row.decision}
                      </Badge>
                    </td>
                    <td className="small">{(row.confidence * 100).toFixed(0)}%</td>
                    <td className="small muted">{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
