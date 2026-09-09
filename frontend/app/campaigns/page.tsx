"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Campaign } from "@/lib/types";
import { RequireSession, Badge, Notice, Empty } from "@/components/Ui";

export default function CampaignsPage() {
  return (
    <RequireSession>
      <Campaigns />
    </RequireSession>
  );
}

function Campaigns() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [segments, setSegments] = useState<any[]>([]);
  const [docs, setDocs] = useState<any[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [active, setActive] = useState<Campaign | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({
    name: "Q4 verification play",
    objective:
      "Book discovery calls with leaders who own prospect data quality",
    tone: "Consultative",
    segment_id: "",
  });

  const load = () => {
    api.get<Campaign[]>("/campaigns").then(setCampaigns).catch((e) => setError(e.message));
    api.get<any[]>("/leads/segments/list").then(setSegments).catch(() => {});
    api
      .get<any[]>("/knowledge/documents")
      .then((d) => {
        setDocs(d);
        setSelectedDocs(d.filter((x) => x.approved).map((x) => x.id));
      })
      .catch(() => {});
  };

  useEffect(load, []);

  const create = async () => {
    try {
      setBusy("create");
      setError("");
      const campaign = await api.post<Campaign>("/campaigns", {
        ...form,
        knowledge_doc_ids: selectedDocs,
      });
      setActive(campaign);
      setMessage("Campaign created. Plan the strategy next.");
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  const plan = async (id: string) => {
    try {
      setBusy("plan");
      const campaign = await api.post<Campaign>(`/campaigns/${id}/strategy`);
      setActive(campaign);
      setMessage("Strategy planned and grounded in approved sources.");
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  const generate = async (id: string) => {
    try {
      setBusy("generate");
      const res = await api.post<any>(`/campaigns/${id}/emails`, {
        lead_ids: [],
        regenerate: false,
      });
      const v = res.compliance.verdicts;
      setMessage(
        `${res.generated.count} drafts generated. Compliance: ${v.APPROVE_FOR_REVIEW} cleared, ${v.NEEDS_REVIEW} need review, ${v.BLOCK} blocked. Open the email studio to approve.`
      );
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Campaigns</h1>
        <p>
          A campaign turns a segment and an objective into a grounded plan, then into
          drafts. Nothing is sent from this screen.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      <Notice kind="success">{message}</Notice>

      <div className="card">
        <h2>New campaign</h2>
        <div className="field">
          <label>Name</label>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="field">
          <label>Objective</label>
          <textarea
            rows={2}
            value={form.objective}
            onChange={(e) => setForm({ ...form, objective: e.target.value })}
          />
        </div>
        <div className="row">
          <div>
            <label>Segment</label>
            <select
              value={form.segment_id}
              onChange={(e) => setForm({ ...form, segment_id: e.target.value })}
            >
              <option value="">Select a segment…</option>
              {segments.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.size})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>Tone</label>
            <select value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })}>
              <option>Consultative</option>
              <option>Direct</option>
              <option>Formal</option>
              <option>Warm</option>
            </select>
          </div>
          <button onClick={create} disabled={!form.segment_id || busy === "create"}>
            Create campaign
          </button>
        </div>

        <h3 style={{ marginTop: 14 }}>Knowledge corpus</h3>
        <p className="hint">
          Only approved documents can be cited. An unapproved draft cannot reach a
          prospect even if someone asks for it.
        </p>
        {docs.map((doc) => (
          <label
            key={doc.id}
            style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 400, marginBottom: 6 }}
          >
            <input
              type="checkbox"
              style={{ width: "auto" }}
              disabled={!doc.approved}
              checked={selectedDocs.includes(doc.id)}
              onChange={(e) =>
                setSelectedDocs(
                  e.target.checked
                    ? [...selectedDocs, doc.id]
                    : selectedDocs.filter((id) => id !== doc.id)
                )
              }
            />
            <span>
              {doc.title}{" "}
              <Badge kind={doc.approved ? "ok" : "bad"}>
                {doc.approved ? "approved" : "not approved"}
              </Badge>{" "}
              <span className="small muted">{doc.chunks} chunks</span>
            </span>
          </label>
        ))}
      </div>

      <div className="card">
        <h2>All campaigns</h2>
        {campaigns.length === 0 ? (
          <Empty>No campaigns yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Drafts</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {campaigns.map((campaign) => (
                  <tr key={campaign.id}>
                    <td>
                      <strong>{campaign.name}</strong>
                      <div className="small muted">{campaign.objective}</div>
                    </td>
                    <td>
                      <Badge kind={campaign.status === "generated" ? "ok" : "neutral"}>
                        {campaign.status}
                      </Badge>
                    </td>
                    <td>{campaign.email_count}</td>
                    <td>
                      <div className="toolbar" style={{ margin: 0 }}>
                        <button
                          className="secondary small"
                          disabled={busy === "plan"}
                          onClick={() => plan(campaign.id)}
                        >
                          Plan strategy
                        </button>
                        <button
                          className="small"
                          disabled={busy === "generate" || !campaign.strategy?.sequence}
                          onClick={() => generate(campaign.id)}
                        >
                          Generate emails
                        </button>
                        <button
                          className="ghost small"
                          onClick={() => setActive(campaign)}
                        >
                          View plan
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {active?.strategy?.sequence && (
        <div className="card">
          <div className="toolbar">
            <h2 style={{ margin: 0 }}>{active.name} — campaign plan</h2>
            <span className="spacer" />
            <span className="small muted">
              groundedness {(active.strategy.groundedness ?? 0).toFixed(2)}
            </span>
            <button className="ghost small" onClick={() => setActive(null)}>
              Close
            </button>
          </div>

          <div className="grid cols-2">
            <div>
              <h3>Audience and value</h3>
              <p className="small">
                <strong>Audience:</strong> {active.strategy.audience}
              </p>
              <p className="small">
                <strong>Pain:</strong> {active.strategy.pain}
              </p>
              <p className="small">
                <strong>Value:</strong> {active.strategy.value_proposition}
              </p>
              <h3 style={{ marginTop: 12 }}>Messaging themes</h3>
              <ul className="small">
                {(active.strategy.messaging_themes || []).map((theme: string) => (
                  <li key={theme}>{theme}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Sequence</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Day</th>
                      <th>Step</th>
                      <th>Goal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(active.strategy.sequence || []).map((step: any, i: number) => (
                      <tr key={i}>
                        <td>{step.day}</td>
                        <td>{step.step}</td>
                        <td className="small">{step.goal}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3 style={{ marginTop: 12 }}>Cited sources</h3>
              {(active.strategy.cited_documents || []).map((doc: any) => (
                <div key={doc.document_id} className="small">
                  {doc.title}{" "}
                  <span className="muted mono">{doc.score?.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
