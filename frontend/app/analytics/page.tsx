"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Campaign } from "@/lib/types";
import { RequireSession, Badge, Notice, Empty } from "@/components/Ui";

export default function AnalyticsPage() {
  return (
    <RequireSession>
      <Analytics />
    </RequireSession>
  );
}

function Analytics() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [data, setData] = useState<any>(null);
  const [costs, setCosts] = useState<any>(null);
  const [replies, setReplies] = useState<any[]>([]);
  const [replyText, setReplyText] = useState(
    "This is timely. Can you do Thursday afternoon for a call?"
  );
  const [leadId, setLeadId] = useState("");
  const [leads, setLeads] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    api.get<Campaign[]>("/campaigns").then((c) => {
      setCampaigns(c);
      if (c.length) setCampaignId(c[0].id);
    });
    api.get<any>("/analytics/costs").then(setCosts).catch(() => {});
    api.get<any[]>("/replies").then(setReplies).catch(() => {});
    api.get<any[]>("/leads").then((l) => {
      setLeads(l);
      if (l.length) setLeadId(l[0].id);
    });
  }, []);

  useEffect(() => {
    if (!campaignId) return;
    api
      .get<any>(`/analytics/campaigns/${campaignId}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [campaignId]);

  const submitReply = async () => {
    try {
      setError("");
      const reply = await api.post<any>("/replies", {
        lead_id: leadId,
        body: replyText,
      });
      setMessage(
        `Classified as ${reply.intent} (${(reply.confidence * 100).toFixed(0)}%). Next: ${reply.next_action}`
      );
      api.get<any[]>("/replies").then(setReplies);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const execute = async (id: string) => {
    try {
      await api.post(`/replies/${id}/execute`);
      setMessage("Action executed and written back to the source CRM.");
      api.get<any[]>("/replies").then(setReplies);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Analytics and replies</h1>
        <p>
          Campaign performance, the cost of running the agents, and inbound reply
          handling with a human gate on anything consequential.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      <Notice kind="success">{message}</Notice>

      <div className="card">
        <div className="row">
          <div>
            <label>Campaign</label>
            <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)}>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {!data ? (
          <Empty>Select a campaign with sent emails.</Empty>
        ) : (
          <>
            <div className="grid cols-4" style={{ marginTop: 14 }}>
              {Object.entries(data.funnel).map(([key, value]) => (
                <div className="stat" key={key}>
                  <div className="label">{key.replace(/_/g, " ")}</div>
                  <div className="value">{value as number}</div>
                </div>
              ))}
            </div>
            <p className="small muted" style={{ marginTop: 10 }}>
              Health {data.health} · delivery {(data.rates.delivery * 100).toFixed(1)}% ·
              bounce {(data.rates.bounce * 100).toFixed(1)}% · reply{" "}
              {(data.rates.reply * 100).toFixed(1)}%
            </p>

            <h3 style={{ marginTop: 14 }}>Recommendations</h3>
            {(data.recommendations || []).length === 0 ? (
              <p className="small muted">Nothing to recommend yet.</p>
            ) : (
              data.recommendations.map((rec: any, i: number) => (
                <div key={i} className="small" style={{ marginBottom: 6 }}>
                  <Badge kind={rec.status === "applied_automatically" ? "ok" : "warn"}>
                    {rec.status.replace(/_/g, " ")}
                  </Badge>{" "}
                  {rec.recommendation}{" "}
                  <span className="muted">({(rec.confidence * 100).toFixed(0)}%)</span>
                </div>
              ))
            )}
          </>
        )}
      </div>

      <div className="card">
        <h2>Simulate an inbound reply</h2>
        <p className="hint">
          The reply agent classifies intent, adjusts the lead score and proposes a
          next action. Anything consequential waits for a human.
        </p>
        <div className="row">
          <div>
            <label>Lead</label>
            <select value={leadId} onChange={(e) => setLeadId(e.target.value)}>
              {leads.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.full_name} — {l.company_name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <label>Reply text</label>
          <textarea rows={3} value={replyText} onChange={(e) => setReplyText(e.target.value)} />
        </div>
        <button onClick={submitReply} disabled={!leadId}>
          Classify reply
        </button>
      </div>

      <div className="card">
        <h2>Reply queue</h2>
        {replies.length === 0 ? (
          <Empty>No replies yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Intent</th>
                  <th>Reply</th>
                  <th>Next action</th>
                  <th>Score</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {replies.map((reply) => (
                  <tr key={reply.id}>
                    <td>
                      <Badge kind={reply.intent === "UNSUBSCRIBE" ? "bad" : "agent"}>
                        {reply.intent}
                      </Badge>
                      <div className="small muted">
                        {(reply.confidence * 100).toFixed(0)}%
                      </div>
                    </td>
                    <td className="small">{reply.body}</td>
                    <td className="small">{reply.next_action}</td>
                    <td className="small">
                      {reply.score_delta > 0 ? `+${reply.score_delta}` : reply.score_delta}
                    </td>
                    <td>
                      {reply.action_status === "proposed" ? (
                        <button className="small" onClick={() => execute(reply.id)}>
                          Approve action
                        </button>
                      ) : (
                        <Badge kind="ok">{reply.action_status}</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {costs && (
        <div className="card">
          <h2>Cost and latency by agent</h2>
          <p className="hint">
            Instrumented from the first build, because unit economics decide whether
            this scales.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Calls</th>
                  <th>Tokens</th>
                  <th>Cost</th>
                  <th>Avg latency</th>
                </tr>
              </thead>
              <tbody>
                {costs.by_agent.map((row: any) => (
                  <tr key={row.agent}>
                    <td className="mono">{row.agent}</td>
                    <td>{row.calls}</td>
                    <td>{row.tokens.toLocaleString()}</td>
                    <td>${row.cost_usd.toFixed(4)}</td>
                    <td>{row.avg_latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">
            Total ${costs.total_cost_usd.toFixed(4)} across {costs.emails_generated}{" "}
            emails — ${costs.cost_per_email.toFixed(4)} per email.
          </p>
        </div>
      )}
    </>
  );
}
