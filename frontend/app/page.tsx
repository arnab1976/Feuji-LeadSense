"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { RequireSession, Notice, Empty } from "@/components/Ui";

type Dashboard = {
  leads: number;
  qualified: number;
  campaigns: number;
  emails_sent: number;
  replies: number;
  open_conflicts: number;
  bands: Record<string, number>;
  leads_by_source: Record<string, number>;
  active_connections: number;
};

export default function DashboardPage() {
  return (
    <RequireSession>
      <Dashboard />
    </RequireSession>
  );
}

function Dashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<Dashboard>("/analytics/dashboard")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <div className="page-head">
        <h1>Revenue operations overview</h1>
        <p>
          Lead volume, qualification and campaign activity for this tenant. Every
          number here traces back to an agent decision you can inspect.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      {!data ? (
        <Empty>Loading…</Empty>
      ) : (
        <>
          <div className="grid cols-4">
            <Stat label="Leads" value={data.leads} sub={`${data.active_connections} active sources`} />
            <Stat label="Qualified (70+)" value={data.qualified} sub="Above campaign threshold" />
            <Stat label="Emails sent" value={data.emails_sent} sub={`${data.replies} replies`} />
            <Stat
              label="Open conflicts"
              value={data.open_conflicts}
              sub={data.open_conflicts ? "Blocking the pipeline" : "Queue is clear"}
            />
          </div>

          <div className="grid cols-2">
            <div className="card">
              <h2>Leads by source</h2>
              <p className="hint">
                The connector layer means these all arrive in the same shape.
              </p>
              <Bars data={data.leads_by_source} />
            </div>
            <div className="card">
              <h2>Score distribution</h2>
              <p className="hint">
                Scoring only runs once verification conflicts are resolved.
              </p>
              {Object.keys(data.bands).length ? (
                <Bars data={data.bands} />
              ) : (
                <p className="small muted">
                  Nothing scored yet. Clear the{" "}
                  <Link href="/verification">verification queue</Link> first.
                </p>
              )}
            </div>
          </div>

          {data.open_conflicts > 0 && (
            <div className="card">
              <h2>Next action</h2>
              <p className="hint">
                {data.open_conflicts} field conflict
                {data.open_conflicts === 1 ? "" : "s"} are holding leads before
                enrichment. Resolve them to release the pipeline.
              </p>
              <Link className="btn" href="/verification">
                Open the verification workbench
              </Link>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Stat({ label, value, sub }: { label: string; value: number; sub: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      <div className="sub">{sub}</div>
    </div>
  );
}

function Bars({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return <p className="small muted">No data yet.</p>;
  return (
    <div>
      {entries.map(([key, value]) => (
        <div key={key} style={{ marginBottom: 10 }}>
          <div className="small" style={{ display: "flex", justifyContent: "space-between" }}>
            <span>{key.replace("_", " ")}</span>
            <strong>{value}</strong>
          </div>
          <div className="meter">
            <span style={{ width: `${(value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
