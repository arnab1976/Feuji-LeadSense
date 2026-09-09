"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Lead } from "@/lib/types";
import { RequireSession, Badge, Notice, Empty, bandKind } from "@/components/Ui";

const WEIGHT_KEYS = [
  "icp_fit",
  "seniority",
  "industry_fit",
  "company_size",
  "technology_fit",
  "engagement",
  "historical_conversion",
];

export default function LeadsPage() {
  return (
    <RequireSession>
      <Leads />
    </RequireSession>
  );
}

function Leads() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [weights, setWeights] = useState<Record<string, number>>({
    icp_fit: 30,
    seniority: 20,
    industry_fit: 15,
    company_size: 10,
    technology_fit: 10,
    engagement: 10,
    historical_conversion: 5,
  });

  const load = () =>
    api.get<Lead[]>("/leads").then(setLeads).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const run = async (path: string, body: unknown, label: string) => {
    try {
      setBusy(label);
      setError("");
      await api.post(path, body);
      setMessage(`${label} complete.`);
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
        <h1>Leads</h1>
        <p>
          Every record with its source, verification state and score. Open a lead to
          see the full decision trail behind its number.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      <Notice kind="success">{message}</Notice>

      <div className="card">
        <h2>Scoring weights</h2>
        <p className="hint">
          Adjust and re-score. Weights here are not saved to tenant policy, so you
          can explore without changing anyone else&apos;s view.
        </p>
        <div className="grid cols-4">
          {WEIGHT_KEYS.map((key) => (
            <div key={key}>
              <label>
                {key.replace(/_/g, " ")} — {weights[key]}
              </label>
              <input
                type="range"
                min={0}
                max={60}
                value={weights[key]}
                onChange={(e) =>
                  setWeights({ ...weights, [key]: Number(e.target.value) })
                }
              />
            </div>
          ))}
        </div>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <button
            className="secondary"
            disabled={!!busy}
            onClick={() => run("/leads/enrich", {}, "Enrichment")}
          >
            Run enrichment
          </button>
          <button
            disabled={!!busy}
            onClick={() => run("/leads/score", { weights }, "Scoring")}
          >
            {busy === "Scoring" ? "Scoring…" : "Re-score with these weights"}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>{leads.length} leads</h2>
        {leads.length === 0 ? (
          <Empty>No leads yet. Sync a source or upload a file.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Title</th>
                  <th>Company</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Persona</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr
                    key={lead.id}
                    style={{ cursor: "pointer" }}
                    onClick={() =>
                      api
                        .get<any>(`/leads/${lead.id}`)
                        .then(setDetail)
                        .catch((e) => setError(e.message))
                    }
                  >
                    <td>
                      <strong>{lead.full_name}</strong>
                      <div className="small muted">{lead.email}</div>
                    </td>
                    <td>{lead.title}</td>
                    <td>{lead.company_name}</td>
                    <td className="mono small">{lead.connector_key}</td>
                    <td>
                      <Badge kind={lead.verification_status === "open" ? "warn" : "ok"}>
                        {lead.status}
                      </Badge>
                    </td>
                    <td className="small">{lead.persona || "—"}</td>
                    <td>
                      {lead.score != null ? (
                        <>
                          <strong>{lead.score}</strong>{" "}
                          <Badge kind={bandKind(lead.band)}>{lead.band}</Badge>
                        </>
                      ) : (
                        <span className="muted small">not scored</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detail && <LeadDetail detail={detail} onClose={() => setDetail(null)} />}
    </>
  );
}

function LeadDetail({ detail, onClose }: { detail: any; onClose: () => void }) {
  const factors = detail.score_detail?.factors || {};
  return (
    <div className="card">
      <div className="toolbar">
        <h2 style={{ margin: 0 }}>{detail.full_name}</h2>
        <span className="small muted">
          {detail.title} · {detail.company_name}
        </span>
        <span className="spacer" />
        <button className="ghost small" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="grid cols-2">
        <div>
          <h3>Verification</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Uploaded</th>
                  <th>Extracted</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {detail.verifications.map((v: any) => (
                  <tr key={v.id}>
                    <td className="mono small">{v.field}</td>
                    <td className="small">{v.uploaded_value}</td>
                    <td className="small">{v.extracted_value}</td>
                    <td>
                      <Badge kind={v.status === "MATCH" ? "ok" : v.status === "MISMATCH" ? "bad" : "warn"}>
                        {v.status}
                      </Badge>
                      {v.resolved_source && (
                        <div className="small muted">
                          {v.resolved_source} · {v.resolved_by || "auto"}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {detail.enrichment && (
            <>
              <h3 style={{ marginTop: 16 }}>Enrichment</h3>
              <p className="small">
                {detail.enrichment.normalized_title} · {detail.enrichment.seniority} ·{" "}
                {detail.enrichment.function} · {detail.enrichment.persona}
              </p>
              <p className="small muted">
                Skills: {(detail.enrichment.skills || []).join(", ") || "—"}
              </p>
            </>
          )}
        </div>

        <div>
          <h3>
            Score{" "}
            {detail.score_detail ? (
              <>
                <strong>{detail.score_detail.score}</strong>{" "}
                <Badge kind={bandKind(detail.score_detail.band)}>
                  {detail.score_detail.band}
                </Badge>
              </>
            ) : (
              <span className="muted">not scored</span>
            )}
          </h3>
          {Object.entries(factors).map(([key, factor]: [string, any]) => (
            <div key={key} style={{ marginBottom: 10 }}>
              <div className="small" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>
                  {key.replace(/_/g, " ")}{" "}
                  <span className="muted">(weight {factor.weight})</span>
                </span>
                <strong>{factor.value}</strong>
              </div>
              <div className="meter">
                <span style={{ width: `${factor.value}%` }} />
              </div>
              <div className="small muted">{factor.evidence}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
