"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import PortalShell from "@/components/PortalShell";
import { api } from "@/lib/api";
import {
  AgentSpec,
  Conflict,
  VerificationWorkbench,
} from "@/lib/types";

const ROSTER_KEYS = [
  "ingestion",
  "verification",
  "enrichment",
  "scoring",
  "segmentation",
  "strategy",
  "email",
] as const;

function agentId(spec: AgentSpec): string {
  return String(spec.number).padStart(2, "0");
}

function rosterAgents(catalog: AgentSpec[]): AgentSpec[] {
  const byKey = new Map(catalog.map((a) => [a.key, a]));
  return ROSTER_KEYS.map((key, index) => {
    const spec = byKey.get(key);
    if (!spec) return null;
    return { ...spec, number: index + 1 };
  }).filter(Boolean) as AgentSpec[];
}

function fieldLabel(field: string): string {
  const map: Record<string, string> = {
    title: "Job title",
    company_name: "Company",
    location: "Location",
    email: "Email",
    phone: "Phone",
  };
  return map[field] || field.replace(/_/g, " ");
}

export default function VerificationPage() {
  return (
    <Suspense fallback={<div className="home-boot">Loading verification…</div>}>
      <VerificationApp />
    </Suspense>
  );
}

function VerificationApp() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workflowFromQuery = searchParams.get("workflow_id") || "";
  const [workflowId, setWorkflowId] = useState(workflowFromQuery);
  const [catalog, setCatalog] = useState<AgentSpec[]>([]);
  const [data, setData] = useState<VerificationWorkbench | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "open" | "all" | "MATCH" | "MISMATCH" | "NEEDS_REVIEW"
  >("open");

  const agents = useMemo(() => rosterAgents(catalog), [catalog]);

  useEffect(() => {
    api
      .get<AgentSpec[]>("/agents/catalog")
      .then(setCatalog)
      .catch(() => setCatalog([]));
  }, []);

  useEffect(() => {
    if (workflowFromQuery) {
      setWorkflowId(workflowFromQuery);
      try {
        window.sessionStorage.setItem("leadsense.workflowId", workflowFromQuery);
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      const saved = window.sessionStorage.getItem("leadsense.workflowId") || "";
      if (saved) setWorkflowId(saved);
    } catch {
      /* ignore */
    }
  }, [workflowFromQuery]);

  const load = () => {
    const qs = new URLSearchParams({ include_matches: "true" });
    if (workflowId) qs.set("workflow_id", workflowId);
    return api
      .get<VerificationWorkbench>(`/leads/verification/queue?${qs}`)
      .then((res) => {
        setData(res);
        if (res.workflow_id) setWorkflowId(res.workflow_id);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(() => {
    setError("");
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId]);

  const stats = data?.stats || {
    match: 0,
    mismatch: 0,
    needs_review: 0,
    resolved: 0,
    open: 0,
    total: 0,
  };
  const items = data?.items || [];

  const openItems = useMemo(
    () =>
      items.filter(
        (row) =>
          row.status !== "MATCH" &&
          !(row.resolved_value && row.resolved_source && row.resolved_source !== "auto")
      ),
    [items]
  );

  const visibleItems = useMemo(() => {
    const isOpen = (row: Conflict) =>
      row.status !== "MATCH" &&
      !(row.resolved_value && row.resolved_source && row.resolved_source !== "auto");

    let rows = items;
    if (statusFilter === "open") rows = items.filter(isOpen);
    else if (statusFilter === "MATCH") rows = items.filter((r) => r.status === "MATCH");
    else if (statusFilter === "MISMATCH")
      rows = items.filter((r) => r.status === "MISMATCH");
    else if (statusFilter === "NEEDS_REVIEW")
      rows = items.filter((r) => r.status === "NEEDS_REVIEW");

    const rank = (row: Conflict) => {
      if (isOpen(row) && row.status === "MISMATCH") return 0;
      if (isOpen(row) && row.status === "NEEDS_REVIEW") return 1;
      if (row.status === "MISMATCH") return 2;
      if (row.status === "NEEDS_REVIEW") return 3;
      return 4;
    };
    return [...rows].sort((a, b) => {
      const d = rank(a) - rank(b);
      if (d !== 0) return d;
      return (a.lead_name || "").localeCompare(b.lead_name || "");
    });
  }, [items, statusFilter]);

  const resolve = async (id: string, resolution: string) => {
    try {
      setBusy(id);
      setError("");
      const res = await api.post<{
        remaining_conflicts?: number;
        pipeline_status?: string;
      }>("/leads/verification/resolve", {
        verification_id: id,
        resolution,
        custom_value: "",
      });
      const resumed =
        res.pipeline_status && res.pipeline_status !== "paused"
          ? ` Orchestrator resumed (${res.pipeline_status}).`
          : "";
      setMessage(
        (res.remaining_conflicts
          ? `Resolved. ${res.remaining_conflicts} conflict(s) remain on this lead.`
          : "Resolved. This lead is now verified.") + resumed
      );
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Resolve failed");
    } finally {
      setBusy("");
    }
  };

  const bulk = async (resolution: string) => {
    try {
      setBusy("bulk");
      setError("");
      const leadIds = Array.from(new Set(openItems.map((r) => r.lead_id)));
      const res = await api.post<{
        resolved: number;
        leads_cleared: number;
        workflows_resumed?: { workflow_id: string; status: string }[];
      }>("/leads/verification/bulk-resolve", {
        resolution,
        lead_ids: leadIds,
      });
      const resumed = (res.workflows_resumed || [])
        .filter((w) => w.status && w.status !== "paused")
        .map((w) => `${w.workflow_id}→${w.status}`)
        .join(", ");
      setMessage(
        `${res.resolved} conflicts resolved across ${res.leads_cleared} leads.` +
          (resumed ? ` Pipeline resumed: ${resumed}.` : "")
      );
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Bulk resolve failed");
    } finally {
      setBusy("");
    }
  };

  const goToEnrichment = () => {
    try {
      window.sessionStorage.setItem("leadsense.selectedAgent", "03");
      if (workflowId) {
        window.sessionStorage.setItem("leadsense.workflowId", workflowId);
      }
    } catch {
      /* ignore */
    }
    router.push(
      workflowId
        ? `/workflow?agent=03&workflow_id=${encodeURIComponent(workflowId)}`
        : "/workflow?agent=03"
    );
  };

  const onSelectAgent = (id: string, key: string) => {
    if (key === "verification") return;
    if (key === "ingestion") {
      router.push(
        workflowId
          ? `/workflow?agent=01&workflow_id=${encodeURIComponent(workflowId)}`
          : "/workflow?agent=01"
      );
      return;
    }
    if (key === "enrichment") {
      goToEnrichment();
      return;
    }
    const num = id;
    router.push(
      workflowId
        ? `/workflow?agent=${num}&workflow_id=${encodeURIComponent(workflowId)}`
        : `/workflow?agent=${num}`
    );
  };

  return (
    <PortalShell
      hideJourney
      sidebar={
        <div className="wf-roster-inner">
          <div className="wf-roster-head">
            <strong>Agent roster</strong>
            <em>Select an agent to open its stage.</em>
          </div>
          <ol className="wf-roster-list">
            {agents.map((agent) => {
              const id = agentId(agent);
              const selected = agent.key === "verification";
              const lit =
                agent.key === "ingestion" ||
                agent.key === "verification" ||
                (stats.open === 0 && stats.total > 0 && agent.key === "enrichment");
              return (
                <li key={agent.key}>
                  <button
                    type="button"
                    className={
                      selected
                        ? "wf-agent selected"
                        : lit
                          ? "wf-agent lit"
                          : "wf-agent"
                    }
                    onClick={() => onSelectAgent(id, agent.key)}
                  >
                    <span className="wf-agent-num">{id}</span>
                    <span className="wf-agent-copy">
                      <strong>{agent.name}</strong>
                      <em>{agent.summary || agent.role}</em>
                    </span>
                    <span
                      className={
                        selected
                          ? "wf-dot warn"
                          : lit
                            ? "wf-dot"
                            : "wf-dot soft"
                      }
                      aria-hidden
                    />
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      }
    >
      <div className="vf-workbench">
      <div className="vf-page-head">
        <div>
          <h1>Verification workbench</h1>
          <p>Resolve each open conflict, or clear the queue in bulk.</p>
          {workflowId ? (
            <p className="small muted" style={{ marginTop: 8 }}>
              Workflow <span className="mono">{workflowId}</span> · from Agent 01
            </p>
          ) : null}
        </div>
      </div>

      {error ? <div className="notice error">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}

      <div className="vf-alert">
        <strong>Human gate — conflict resolution</strong>
        <p>
          {stats.open > 0
            ? `${stats.open} record${stats.open === 1 ? "" : "s"} cannot continue until a reviewer decides which value to trust. Choose which side to keep below, or clear the queue in bulk.`
            : stats.total > 0
              ? "Queue is clear for this workflow. Continue to Enrichment when you are ready."
              : "No verification rows yet. Run Connect & Import on Agent 01 so Extraction can feed this bench."}
        </p>
      </div>

      <div className="vf-stats">
        <div className="vf-stat match">
          <span>Match</span>
          <strong>{stats.match}</strong>
          <em>straight through</em>
        </div>
        <div className="vf-stat mismatch">
          <span>Mismatch</span>
          <strong>{stats.mismatch}</strong>
          <em>material difference</em>
        </div>
        <div className="vf-stat review">
          <span>Needs review</span>
          <strong>{stats.needs_review}</strong>
          <em>below threshold</em>
        </div>
        <div className="vf-stat resolved">
          <span>Resolved by you</span>
          <strong>{stats.resolved}</strong>
          <em>human override logged</em>
        </div>
      </div>

      <div className="toolbar vf-toolbar">
        <strong>{stats.open}</strong>
        <span className="small muted">
          open · {stats.total} field row{stats.total === 1 ? "" : "s"}
        </span>
        <span className="spacer" />
        <button
          className="secondary"
          disabled={!openItems.length || busy === "bulk"}
          onClick={() => void bulk("extracted")}
        >
          Accept all extracted
        </button>
        <button
          className="ghost"
          disabled={!openItems.length || busy === "bulk"}
          onClick={() => void bulk("uploaded")}
        >
          Keep all uploaded
        </button>
      </div>

      <section className="card vf-table-card" aria-label="Field-level reconciliation">
        <div className="vf-table-head">
          <div className="vf-table-head-copy">
            <h2>Field-level reconciliation</h2>
            <p className="hint" style={{ margin: 0 }}>
              Compare Uploaded vs Extracted. Filter by status — open mismatches
              need a trusted value before Enrichment.
            </p>
          </div>
          <div className="vf-filter-bar" role="tablist" aria-label="Status filter">
            {(
              [
                ["open", `Open (${stats.open})`],
                ["MISMATCH", `Mismatch (${stats.mismatch})`],
                ["NEEDS_REVIEW", `Review (${stats.needs_review})`],
                ["MATCH", `Match (${stats.match})`],
                ["all", `All (${stats.total})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={statusFilter === key}
                className={
                  statusFilter === key ? "vf-filter active" : "vf-filter"
                }
                onClick={() => setStatusFilter(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {items.length === 0 ? (
          <p className="hint" style={{ marginBottom: 0 }}>
            No rows for this scope yet.
          </p>
        ) : visibleItems.length === 0 ? (
          <p className="hint" style={{ marginBottom: 0 }}>
            No rows in this filter. Switch to All or another status.
          </p>
        ) : (
          <div className="vf-table-window">
            <div className="vf-table-wrap">
              <table className="vf-table">
                <thead>
                  <tr>
                    <th>Lead</th>
                    <th>Field</th>
                    <th>Uploaded</th>
                    <th>Extracted</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Resolution</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleItems.map((row) => (
                    <VerificationRow
                      key={row.verification_id}
                      row={row}
                      busy={busy === row.verification_id}
                      onResolve={resolve}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <div className="wf-footer">
        <div className="wf-info">
          {stats.open > 0
            ? "Resolve open conflicts in the table above, then Continue to Enrichment when the queue is clear."
            : "Verification is ready. Continue to Enrichment to open the next agent."}
        </div>
        <button
          type="button"
          className="wf-continue"
          onClick={goToEnrichment}
        >
          Continue to Enrichment
        </button>
      </div>
      </div>
    </PortalShell>
  );
}

function VerificationRow({
  row,
  busy,
  onResolve,
}: {
  row: Conflict;
  busy: boolean;
  onResolve: (id: string, resolution: string) => void;
}) {
  const isMatch = row.status === "MATCH";
  const humanResolved =
    Boolean(row.resolved_value) &&
    (row.resolved_source === "uploaded" ||
      row.resolved_source === "extracted" ||
      row.resolved_source === "custom");
  const needsAction = !isMatch && !row.resolved_value;
  const conf = Math.max(0, Math.min(1, Number(row.confidence) || 0));
  const confTone =
    row.status === "MATCH"
      ? "high"
      : row.status === "NEEDS_REVIEW"
        ? "mid"
        : "low";

  return (
    <tr className={`vf-row status-${row.status.toLowerCase()}${needsAction ? " open" : ""}`}>
      <td className="vf-lead-cell">
        <strong className="vf-lead-name" title={row.lead_name || undefined}>
          {row.lead_name || "—"}
        </strong>
        <div className="mono small muted vf-lead-id" title={row.lead_id}>
          {row.lead_id.length > 12
            ? `${row.lead_id.slice(0, 8)}…${row.lead_id.slice(-4)}`
            : row.lead_id}
        </div>
      </td>
      <td className="vf-value-cell">{fieldLabel(row.field)}</td>
      <td className="vf-value-cell" title={row.uploaded_value || undefined}>
        {row.uploaded_value || <em className="muted">empty</em>}
      </td>
      <td className="vf-value-cell" title={row.extracted_value || undefined}>
        {row.extracted_value || <em className="muted">empty</em>}
      </td>
      <td>
        <span className={`vf-badge status-${row.status.toLowerCase()}`}>
          {row.status.replace("_", " ")}
        </span>
        <div className="vf-reason" title={row.reason || undefined}>
          {row.reason}
        </div>
      </td>
      <td>
        <div className={`vf-conf tone-${confTone}`}>
          <span className="vf-conf-bar" aria-hidden>
            <i style={{ width: `${Math.round(conf * 100)}%` }} />
          </span>
          <strong className="mono">{conf.toFixed(2)}</strong>
        </div>
      </td>
      <td>
        {isMatch || (row.resolved_source === "auto" && isMatch) ? (
          <button type="button" className="vf-res-btn muted" disabled>
            auto-accepted
          </button>
        ) : humanResolved ? (
          <button type="button" className="vf-res-btn chosen" disabled>
            kept {row.resolved_source}
          </button>
        ) : needsAction ? (
          <div className="vf-resolve">
            <button
              type="button"
              className="vf-res-btn"
              disabled={busy}
              onClick={() => onResolve(row.verification_id, "uploaded")}
            >
              kept uploaded
            </button>
            <button
              type="button"
              className="vf-res-btn"
              disabled={busy}
              onClick={() => onResolve(row.verification_id, "extracted")}
            >
              kept extracted
            </button>
          </div>
        ) : (
          <button type="button" className="vf-res-btn muted" disabled>
            auto-accepted
          </button>
        )}
      </td>
    </tr>
  );
}
