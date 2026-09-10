"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import PortalShell from "@/components/PortalShell";
import { api, ApiError } from "@/lib/api";
import {
  AgentDecision,
  AgentExecution,
  AgentSpec,
  ConnectImportResult,
  Connector,
  FixturePreview,
  SourceConnection,
  UploadResult,
  WorkflowDetail,
  WorkflowHistoryEntry,
} from "@/lib/types";

/** Lead-processing agents shown in the Workflow roster (Orchestrator is the bot).
 *  Extraction still runs in the backend pipeline but is not a separate roster step —
 *  Agent 01 Continue goes directly to Verification. */
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

const SOURCE_CONNECTORS = [
  { key: "salesforce", label: "Salesforce CRM" },
  { key: "hubspot", label: "HubSpot CRM" },
  { key: "manual_upload", label: "Manual Upload CSV/Excel" },
  { key: "zoominfo", label: "ZoomInfo Enrichment" },
  { key: "web_profile", label: "Web Profile Public pages" },
  { key: "csv_url", label: "CSV Feed URL/S3" },
  { key: "apollo", label: "Apollo.io Enrichment" },
];

const LISTS = [
  {
    id: "sf-bfsi",
    title: "BFSI prospect list",
    industry: "BFSI",
    description:
      "Banking, insurance and capital-markets leaders across India and the Gulf.",
    rows: 50,
    regions: "India, UAE, Singapore, UK",
    coverage: "Operations, risk, claims, data and transformation leaders",
    file: "salesforce_bfsi_prospect_list.csv",
    connector_key: "salesforce",
    mode: "sync" as const,
  },
  {
    id: "sf-tech",
    title: "Technology buyers (CRM)",
    industry: "Technology",
    description:
      "Platform and engineering buyers synced from Salesforce demo accounts.",
    rows: 50,
    regions: "India, Singapore, Germany, US",
    coverage: "Engineering, product, platform and data leaders",
    file: "salesforce_technology_buyers_crm.csv",
    connector_key: "salesforce",
    mode: "sync" as const,
  },
  {
    id: "hs-life",
    title: "Life sciences list",
    industry: "Life sciences",
    description:
      "Manufacturing and quality leaders at mid-market pharma and medtech.",
    rows: 50,
    regions: "Denmark, Switzerland, India, Ireland, US",
    coverage: "Plant IT, quality systems, validation and digital manufacturing",
    file: "hubspot_lifesciences_list.csv",
    connector_key: "hubspot",
    mode: "sync" as const,
  },
  {
    id: "hs-bfsi",
    title: "BFSI nurture list",
    industry: "BFSI",
    description:
      "Insurance and banking contacts staged in HubSpot marketing lists.",
    rows: 50,
    regions: "India, UK, UAE, South Africa",
    coverage: "Marketing-qualified BFSI demand and nurture contacts",
    file: "hubspot_bfsi_nurture_list.csv",
    connector_key: "hubspot",
    mode: "sync" as const,
  },
  {
    id: "zi-tech",
    title: "Tech enrichment pack",
    industry: "Technology",
    description:
      "SaaS and IT-services contacts enriched via ZoomInfo demo mode.",
    rows: 50,
    regions: "US, Germany, India, Singapore",
    coverage: "Firmographic and technographic screening for tech accounts",
    file: "zoominfo_tech_enrichment_pack.csv",
    connector_key: "zoominfo",
    mode: "sync" as const,
  },
  {
    id: "zi-life",
    title: "Pharma enrichment pack",
    industry: "Life sciences",
    description:
      "Life-sciences operators pulled through ZoomInfo firmographic filters.",
    rows: 50,
    regions: "US, Switzerland, Denmark, India",
    coverage: "Manufacturing, QA, supply-chain and compliance personas",
    file: "zoominfo_pharma_enrichment_pack.csv",
    connector_key: "zoominfo",
    mode: "sync" as const,
  },
  {
    id: "ap-tech",
    title: "Apollo SaaS targets",
    industry: "Technology",
    description:
      "VP Engineering / CDO titles from Apollo person search (demo).",
    rows: 50,
    regions: "US, Canada, India, Germany",
    coverage: "Outbound prospecting for SaaS engineering and data personas",
    file: "apollo_saas_targets.csv",
    connector_key: "apollo",
    mode: "sync" as const,
  },
  {
    id: "ap-bfsi",
    title: "Apollo BFSI targets",
    industry: "BFSI",
    description:
      "Banking and insurance operators from Apollo title filters (demo).",
    rows: 50,
    regions: "India, UK, UAE, Nigeria",
    coverage: "Banking, insurance and financial-ops buying committee roles",
    file: "apollo_bfsi_targets.csv",
    connector_key: "apollo",
    mode: "sync" as const,
  },
  {
    id: "csv-multi",
    title: "CSV feed — mixed industries",
    industry: "Cross-industry",
    description:
      "Scheduled CSV/S3 feed spanning BFSI, life sciences and technology rows.",
    rows: 50,
    regions: "Global mixed feed",
    coverage: "Cross-industry batch with balanced functions and company sizes",
    file: "csv_url_mixed_industry_feed.csv",
    connector_key: "csv_url",
    mode: "sync" as const,
  },
  {
    id: "web-tech",
    title: "Public profile scrape",
    industry: "Technology",
    description:
      "Public team pages for software and IT-services accounts (policy-gated).",
    rows: 50,
    regions: "US, Germany, Singapore, India",
    coverage: "Public bios and team pages for tech accounts",
    file: "web_profile_public_team_pages.csv",
    connector_key: "web_profile",
    mode: "sync" as const,
  },
  {
    id: "mu-tech",
    title: "Technology buyers (upload)",
    industry: "Technology",
    description:
      "Data and platform engineering leaders at SaaS scale-ups — upload or demo CSV.",
    rows: 50,
    regions: "India, Singapore, US, Germany",
    coverage: "Upload-ready tech buyers with full canonical fields",
    file: "manual_upload_technology_buyers.csv",
    connector_key: "manual_upload",
    mode: "upload" as const,
  },
  {
    id: "mu-life",
    title: "Life sciences (upload)",
    industry: "Life sciences",
    description:
      "Upload a pharma/medtech sheet or use the demo life-sciences CSV.",
    rows: 50,
    regions: "Denmark, Switzerland, India, Ireland, US",
    coverage: "Upload-ready life-sciences contacts with quality and operations focus",
    file: "manual_upload_lifesciences.csv",
    connector_key: "manual_upload",
    mode: "upload" as const,
  },
  {
    id: "mu-bfsi",
    title: "BFSI (upload)",
    industry: "BFSI",
    description:
      "Upload a banking/insurance sheet or use the demo BFSI pack.",
    rows: 50,
    regions: "India, UAE, UK, Singapore",
    coverage: "Upload-ready BFSI contacts across operations, risk and data",
    file: "manual_upload_bfsi.csv",
    connector_key: "manual_upload",
    mode: "upload" as const,
  },
];

type ProspectList = (typeof LISTS)[number];
type ExternalImportPhase = "review" | "streaming" | "results" | null;
type IngestLogLevel = "info" | "ok" | "warn" | "err";
type IngestLogLine = { at: string; text: string; level: IngestLogLevel };

function bfsiListForConnector(connectorKey: string): ProspectList | null {
  return (
    LISTS.find((l) => l.connector_key === connectorKey && l.industry === "BFSI") ||
    LISTS.find((l) => l.connector_key === connectorKey) ||
    null
  );
}

function stagingFileLabel(list: ProspectList | null, connectorKey: string): string {
  if (list?.file) {
    return list.file.replace(/\.csv$/i, ".xlsx");
  }
  return `${connectorKey}_bfsi_targets_q3.xlsx`;
}

function formatLogTime(d: Date): string {
  return d.toLocaleTimeString("en-GB", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function buildIngestLogScript(
  sync: NonNullable<ConnectImportResult["sync"]>,
  fileLabel: string,
  tenantLabel: string
): IngestLogLine[] {
  const fetched = sync.fetched || 0;
  const created = sync.created || 0;
  const duplicates = sync.duplicates || 0;
  const invalid = sync.invalid || 0;
  const base = new Date();
  const stamp = (offsetSec: number) => {
    const d = new Date(base.getTime() + offsetSec * 1000);
    return formatLogTime(d);
  };
  return [
    {
      at: stamp(0),
      text: `Reading ${fileLabel} from S3 staging bucket`,
      level: "info",
    },
    {
      at: stamp(0),
      text: "Schema validation passed - 6 of 6 required fields present",
      level: "ok",
    },
    {
      at: stamp(0),
      text: `Applying tenant column mapping rules for ${tenantLabel}`,
      level: "info",
    },
    {
      at: stamp(1),
      text: `${fetched} rows parsed`,
      level: "ok",
    },
    {
      at: stamp(1),
      text: `${invalid} rows failed syntax validation and were quarantined`,
      level: "err",
    },
    {
      at: stamp(1),
      text: `${duplicates} duplicate records collapsed by email and company key`,
      level: "warn",
    },
    {
      at: stamp(2),
      text: `${created} valid lead records persisted`,
      level: "ok",
    },
    {
      at: stamp(2),
      text: "Background extraction queued via Celery",
      level: "info",
    },
  ];
}

type PipelinePhase =
  | "idle"
  | "running"
  | "paused"
  | "completed"
  | "error";

type RunState = {
  phase: PipelinePhase;
  workflowId: string;
  currentNode: string;
  pausedAt: string | null;
  openConflicts: number;
  created: number;
  leadIds: string[];
  message: string;
};

function nodeToStep(currentNode: string, status: string, pausedAt: string | null): number {
  if (status === "paused" || pausedAt === "verification") return 4;
  const node = currentNode || "";
  if (node.includes("complete") || status === "completed") return 6;
  if (node.includes("scoring")) return 6;
  if (node.includes("enrichment")) return 5;
  if (node.includes("verification")) return 4;
  if (node.includes("extraction")) return 3;
  if (node.includes("pipeline.start") || node.includes("pipeline.resume")) return 2;
  if (node.includes("ingestion")) return 1;
  return 1;
}

function agentForPhase(activeStep: number, phase: PipelinePhase, currentNode: string): string {
  // Roster: 01 Ingestion → 02 Verification → 03 Enrichment → 04 Scoring …
  // Backend extraction (step 3) is skipped in the UI and maps to Verification.
  if (phase === "paused" || activeStep === 4) return "02";
  if (activeStep >= 6) return "04";
  if (activeStep === 5) return "03";
  if (activeStep === 3) return "02";
  if (activeStep === 2 || currentNode.includes("pipeline.")) return "01";
  return "01";
}

const JOURNEY_STEPS = [
  { key: "ingestion", label: "01 Ingestion", detail: "Validate, dedupe, persist leads" },
  { key: "pipeline.start", label: "Orchestrator", detail: "Hand-off lead_ids · start pipeline" },
  { key: "extraction", label: "Extraction (auto)", detail: "Canonical profile beside upload" },
  { key: "verification", label: "02 Verification", detail: "Human gate · compare fields" },
  { key: "enrichment", label: "03 Enrichment", detail: "Seniority, persona, firmographics" },
  { key: "scoring", label: "04 Scoring", detail: "ICP band + factor evidence" },
];

function journeyFocus(currentNode: string, phase: PipelinePhase): string {
  if (phase === "paused" || currentNode.includes("verification")) return "verification";
  if (currentNode.includes("scoring") || currentNode.includes("complete")) return "scoring";
  if (currentNode.includes("enrichment")) return "enrichment";
  if (currentNode.includes("extraction")) return "extraction";
  if (currentNode.includes("pipeline")) return "pipeline.start";
  if (currentNode.includes("ingestion")) return "ingestion";
  if (phase === "completed") return "scoring";
  return "ingestion";
}

function journeyNarrative(
  phase: PipelinePhase,
  currentNode: string,
  openConflicts: number,
  created: number,
  busy: boolean
): { headline: string; body: string } {
  if (phase === "idle" && !busy) {
    return {
      headline: "Waiting to start the lead journey",
      body: "Pick a prospect list on Agent 01, then Continue. The Orchestrator will track Ingestion → Extraction → Verification → Enrichment → Scoring.",
    };
  }
  if (busy || phase === "running") {
    const focus = journeyFocus(currentNode, phase);
    const step = JOURNEY_STEPS.find((s) => s.key === focus);
    return {
      headline: `Now: ${step?.label || currentNode || "pipeline"}`,
      body: `${step?.detail || "Advancing the pipeline."} Checkpoints below update as each agent finishes.`,
    };
  }
  if (phase === "paused") {
    return {
      headline: "Paused for human review",
      body: `Verification found ${openConflicts || "open"} conflict(s). Enrichment and scoring stay blocked until you resolve fields in the workbench — then the Orchestrator resumes automatically.`,
    };
  }
  if (phase === "completed") {
    return {
      headline: "Journey complete through scoring",
      body: created
        ? `${created} lead(s) finished Ingestion → Extraction → Verification → Enrichment → Scoring. Open Leads or Analytics for bands and evidence.`
        : "Pipeline completed. Open Leads or Analytics for scored results.",
    };
  }
  if (phase === "error") {
    return {
      headline: "Pipeline stopped with an error",
      body: "Fix the issue, then run Continue again from Agent 01. Prior checkpoints remain in the timeline when available.",
    };
  }
  return {
    headline: "Pipeline control",
    body: "Watch the overall agent journey here while you work in the main canvas.",
  };
}

function journeyStepState(
  stepKey: string,
  focus: string,
  phase: PipelinePhase,
  history: WorkflowHistoryEntry[]
): "done" | "active" | "todo" | "paused" {
  const order = JOURNEY_STEPS.map((s) => s.key);
  const focusIdx = order.indexOf(focus);
  const stepIdx = order.indexOf(stepKey);
  const seen = history.some(
    (h) => h.node === stepKey || h.node.startsWith(stepKey.split(".")[0])
  );
  if (phase === "paused" && stepKey === "verification") return "paused";
  if (phase === "completed" && stepIdx <= order.indexOf("scoring")) return "done";
  if (stepKey === focus && (phase === "running" || phase === "paused")) return "active";
  if (seen && stepIdx < focusIdx) return "done";
  if (stepIdx < focusIdx) return "done";
  if (stepKey === focus) return "active";
  return "todo";
}

function formatCheckpointTime(at?: string): string {
  if (!at) return "";
  try {
    const d = new Date(at);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return at;
  }
}

function checkpointLabel(node: string): string {
  const map: Record<string, string> = {
    ingestion: "Ingestion hand-off",
    "pipeline.start": "Pipeline start",
    "pipeline.resume": "Pipeline resume",
    "pipeline.complete": "Pipeline complete",
    extraction: "Extraction",
    verification: "Verification",
    enrichment: "Enrichment",
    scoring: "Scoring",
  };
  if (map[node]) return map[node];
  if (node.endsWith(".skipped")) return `${node.replace(".skipped", "")} skipped`;
  return node;
}

function CheckpointTimeline({
  history,
  currentNode,
  status,
  pausedReason,
  nextAction,
  live,
  compact = false,
}: {
  history: WorkflowHistoryEntry[];
  currentNode: string;
  status: string;
  pausedReason?: string;
  nextAction?: string;
  live: boolean;
  compact?: boolean;
}) {
  const entries = history.length ? history : [];
  return (
    <div className={`wf-timeline ${live ? "live" : ""} ${compact ? "compact" : ""}`}>
      <div className="wf-timeline-head">
        <strong>Live checkpoint timeline</strong>
        {live ? <span className="wf-live-pill">Live</span> : null}
        {status ? (
          <span className={`wf-timeline-status status-${status}`}>{status}</span>
        ) : null}
      </div>
      {entries.length === 0 ? (
        <p className="hint" style={{ margin: 0 }}>
          Waiting for the first checkpoint. Start Agent 01 → Continue.
        </p>
      ) : (
        <ol className="wf-timeline-list">
          {entries.map((entry, idx) => {
            const isLatest = idx === entries.length - 1;
            const isCurrent = entry.node === currentNode || isLatest;
            return (
              <li
                key={`${entry.node}-${entry.at || idx}`}
                className={[
                  "wf-timeline-item",
                  entry.status,
                  isCurrent ? "current" : "",
                  isLatest && live ? "pulse" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span className="wf-timeline-marker" aria-hidden />
                <div className="wf-timeline-body">
                  <div className="wf-timeline-row">
                    <strong>{checkpointLabel(entry.node)}</strong>
                    {!compact ? (
                      <span className="mono small">{entry.node}</span>
                    ) : null}
                  </div>
                  <div className="wf-timeline-meta">
                    <span>{entry.status}</span>
                    {entry.next_action ? <span>next → {entry.next_action}</span> : null}
                    {entry.at ? <span>{formatCheckpointTime(entry.at)}</span> : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {(pausedReason || nextAction) && (
        <p className="wf-timeline-foot">
          {pausedReason ? <span>Paused: {pausedReason}</span> : null}
          {nextAction ? <span> Next action: {nextAction}</span> : null}
        </p>
      )}
    </div>
  );
}

function OrchestratorBot({
  open,
  minimized,
  onOpen,
  onClose,
  onMinimize,
  history,
  currentNode,
  status,
  pausedReason,
  nextAction,
  live,
  phase,
  workflowId,
  openConflicts,
  created,
  busy,
  onResume,
}: {
  open: boolean;
  minimized: boolean;
  onOpen: () => void;
  onClose: () => void;
  onMinimize: () => void;
  history: WorkflowHistoryEntry[];
  currentNode: string;
  status: string;
  pausedReason?: string;
  nextAction?: string;
  live: boolean;
  phase: PipelinePhase;
  workflowId: string;
  openConflicts: number;
  created: number;
  busy: boolean;
  onResume: () => void;
}) {
  const statusLabel =
    phase === "idle" ? "Idle" : phase === "running" || busy ? "Running" : phase;
  const focus = journeyFocus(currentNode, phase);
  const story = journeyNarrative(phase, currentNode, openConflicts, created, busy);
  const dragRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const dragState = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    origLeft: number;
    origTop: number;
    moved: boolean;
  } | null>(null);
  const DRAG_THRESHOLD_PX = 8;

  const clampPos = (left: number, top: number, el?: HTMLElement | null) => {
    const width = el?.offsetWidth || (minimized ? 200 : 340);
    const height = el?.offsetHeight || (minimized ? 52 : 420);
    const roster = document.querySelector(".wf-roster") as HTMLElement | null;
    const topBar = document.querySelector(".wf-top") as HTMLElement | null;
    const minLeft = roster ? Math.ceil(roster.getBoundingClientRect().right) + 8 : 12;
    const minTop = topBar ? Math.ceil(topBar.getBoundingClientRect().bottom) + 8 : 66;
    const maxLeft = Math.max(minLeft, window.innerWidth - width - 12);
    const maxTop = Math.max(minTop, window.innerHeight - height - 12);
    return {
      left: Math.min(maxLeft, Math.max(minLeft, left)),
      top: Math.min(maxTop, Math.max(minTop, top)),
    };
  };

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("leadsense.orchPos");
      if (!raw) return;
      const parsed = JSON.parse(raw) as { left: number; top: number };
      if (typeof parsed.left === "number" && typeof parsed.top === "number") {
        setPos(clampPos(parsed.left, parsed.top));
      }
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onResize = () => {
      setPos((prev) => {
        if (!prev) return prev;
        return clampPos(prev.left, prev.top, dragRef.current);
      });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minimized, open]);

  const style =
    pos != null
      ? ({ left: pos.left, top: pos.top, right: "auto", bottom: "auto" } as const)
      : undefined;

  const beginDrag = (e: ReactPointerEvent, el: HTMLElement) => {
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (
      target.closest(
        "a, .orch-bot-actions button, .orch-bot-cta a, .orch-bot-cta button, input, select, textarea"
      )
    ) {
      return;
    }
    const rect = el.getBoundingClientRect();
    const current = pos || { left: rect.left, top: rect.top };
    dragState.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      origLeft: current.left,
      origTop: current.top,
      moved: false,
    };
    el.setPointerCapture(e.pointerId);
  };

  const moveDrag = (e: ReactPointerEvent) => {
    const state = dragState.current;
    if (!state || state.pointerId !== e.pointerId) return;
    const dx = e.clientX - state.startX;
    const dy = e.clientY - state.startY;
    if (!state.moved && (Math.abs(dx) > DRAG_THRESHOLD_PX || Math.abs(dy) > DRAG_THRESHOLD_PX)) {
      state.moved = true;
    }
    if (!state.moved) return;
    e.preventDefault();
    setPos(clampPos(state.origLeft + dx, state.origTop + dy, dragRef.current));
  };

  const endDrag = (e: ReactPointerEvent, onTap?: () => void) => {
    const state = dragState.current;
    if (!state || state.pointerId !== e.pointerId) return;
    const moved = state.moved;
    dragState.current = null;
    try {
      dragRef.current?.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    if (!moved) {
      onTap?.();
      return;
    }
    setPos((prev) => {
      if (!prev) return prev;
      const next = clampPos(prev.left, prev.top, dragRef.current);
      try {
        window.localStorage.setItem("leadsense.orchPos", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  if (!open || minimized) {
    return (
      <div
        ref={dragRef}
        className="orch-bot-dock"
        style={style}
        onPointerDown={(e) => {
          if (dragRef.current) beginDrag(e, dragRef.current);
        }}
        onPointerMove={moveDrag}
        onPointerUp={(e) => endDrag(e, onOpen)}
        onPointerCancel={(e) => endDrag(e)}
      >
        <button
          type="button"
          className={`orch-bot-fab ${live ? "live" : ""} status-${phase}`}
          // Open is handled on pointer-up (tap vs drag). Prevent duplicate click.
          onClick={(e) => e.preventDefault()}
          aria-label="Open Workflow Orchestrator"
          aria-expanded={false}
        >
          <span className="orch-bot-fab-pulse" aria-hidden />
          <span className="orch-bot-fab-label">
            <strong>Orchestrator</strong>
            <em>{story.headline}</em>
          </span>
          {(phase === "paused" || live) && (
            <span className="orch-bot-fab-badge">
              {phase === "paused" ? openConflicts || "!" : "•"}
            </span>
          )}
        </button>
      </div>
    );
  }

  return (
    <aside
      ref={dragRef}
      className="orch-bot"
      aria-label="Workflow Orchestrator"
      style={style}
      onPointerDown={(e) => {
        if (dragRef.current) beginDrag(e, dragRef.current);
      }}
      onPointerMove={moveDrag}
      onPointerUp={(e) => endDrag(e)}
      onPointerCancel={(e) => endDrag(e)}
    >
      <header className="orch-bot-head orch-bot-drag-handle">
        <div>
          <div className="orch-bot-kicker">System · Journey control · Drag to move</div>
          <strong>Workflow Orchestrator</strong>
          <div className="orch-bot-status-line">{statusLabel}</div>
        </div>
        <div className="orch-bot-actions">
          <button
            type="button"
            className="orch-bot-icon"
            onClick={(e) => {
              e.stopPropagation();
              onMinimize();
            }}
            title="Minimize"
          >
            —
          </button>
          <button
            type="button"
            className="orch-bot-icon"
            onClick={(e) => {
              e.stopPropagation();
              onMinimize();
            }}
            title="Dock Orchestrator"
          >
            ×
          </button>
        </div>
      </header>
      <div className="orch-bot-body">
        <div className="orch-bot-story">
          <strong>{story.headline}</strong>
          <p>{story.body}</p>
        </div>

        <div className="orch-journey" aria-label="Overall agent journey">
          {JOURNEY_STEPS.map((step) => {
            const state = journeyStepState(step.key, focus, phase, history);
            return (
              <div key={step.key} className={`orch-journey-step ${state}`}>
                <span className="orch-journey-dot" aria-hidden />
                <div>
                  <strong>{step.label}</strong>
                  <em>{step.detail}</em>
                </div>
              </div>
            );
          })}
        </div>

        <CheckpointTimeline
          history={history}
          currentNode={currentNode}
          status={status}
          pausedReason={pausedReason}
          nextAction={nextAction}
          live={live}
          compact
        />
        {phase === "paused" ? (
          <div className="orch-bot-cta">
            <Link className="btn" href="/verification">
              Open human review
            </Link>
            <button
              type="button"
              className="secondary"
              disabled={busy || !workflowId}
              onClick={onResume}
            >
              Try resume
            </button>
          </div>
        ) : workflowId && workflowId !== "pending" ? (
          <p className="orch-bot-meta">
            Workflow <span className="mono">{workflowId}</span>
            {currentNode ? ` · ${currentNode}` : ""}
            {nextAction ? ` · next ${nextAction}` : ""}
          </p>
        ) : (
          <p className="orch-bot-meta">
            The main canvas is for agents. This bot narrates the full journey as
            checkpoints are written.
          </p>
        )}
      </div>
    </aside>
  );
}

function buildTechCsv(): Blob {
  const rows = [
    ["full_name", "email", "title", "company_name", "location"],
    ["Aisha Rahman", "aisha.rahman@nimbus.io", "VP Engineering", "Nimbus Data", "Bengaluru"],
    ["Marcus Chen", "marcus.chen@orbitly.ai", "Director of Platform", "Orbitly", "Singapore"],
    ["Priya Nair", "priya.nair@stacklane.com", "Head of Data", "Stacklane", "Hyderabad"],
    ["Jonah Wells", "jonah.wells@brightops.io", "CTO", "BrightOps", "Austin"],
    ["Elena Petrova", "elena.petrova@quantora.com", "VP Product", "Quantora", "Berlin"],
  ];
  const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
  return new Blob([csv], { type: "text/csv" });
}

function agentRuntimeBadge(
  agentKey: string,
  phase: PipelinePhase,
  currentNode: string,
  busy: boolean
): string | null {
  const focus = journeyFocus(currentNode, phase);
  const focusKey =
    focus === "pipeline.start" ? "ingestion" : focus === "scoring" && phase === "completed" ? "" : focus;
  if (phase === "paused" && agentKey === "verification") return "Awaiting human";
  if ((phase === "running" || busy) && focusKey === agentKey) return "Running now";
  if (phase === "completed" && agentKey === "scoring" && focus === "scoring") return "Completed";
  return null;
}

function DecisionRecord({
  agent,
  workflowId,
  latest,
}: {
  agent: AgentSpec;
  workflowId: string;
  latest: AgentDecision | null;
}) {
  const record = latest
    ? {
        tenant_id: "session",
        workflow_id: latest.workflow_id || workflowId || null,
        agent: latest.agent,
        decision: latest.decision,
        confidence: latest.confidence,
        reason: latest.reason || null,
        model_or_rule_version: latest.model_or_rule_version || agent.version || `${agent.key}-v1`,
        human_override: latest.human_override,
      }
    : {
        tenant_id: "session",
        workflow_id: workflowId || null,
        agent: `${agent.key}_agent`,
        decision: "<classification>",
        confidence: 0.0,
        reason: "<evidence>",
        model_or_rule_version: agent.version || `${agent.key}-v1`,
        human_override: false,
      };
  const lines = JSON.stringify(record, null, 2).split("\n");
  return (
    <pre className="agent-drawer-code" aria-label="Decision record">
      {lines.map((line, i) => {
        const m = line.match(/^(\s*)"([^"]+)":\s*(.*?)(,?)$/);
        if (!m) {
          return (
            <span key={i} className="code-plain">
              {line}
              {"\n"}
            </span>
          );
        }
        const [, indent, key, raw, comma] = m;
        let valueNode: ReactNode = <span className="code-plain">{raw}</span>;
        if (raw === "false" || raw === "true" || raw === "null") {
          valueNode = <span className="code-bool">{raw}</span>;
        } else if (/^-?\d+(\.\d+)?$/.test(raw)) {
          valueNode = <span className="code-num">{raw}</span>;
        } else if (raw.startsWith('"')) {
          const inner = raw.slice(1, -1);
          valueNode =
            inner.startsWith("<") && inner.endsWith(">") ? (
              <span className="code-ph">&quot;{inner}&quot;</span>
            ) : (
              <span className="code-str">&quot;{inner}&quot;</span>
            );
        }
        return (
          <span key={i}>
            {indent}
            <span className="code-key">&quot;{key}&quot;</span>
            <span className="code-plain">: </span>
            {valueNode}
            <span className="code-plain">{comma}</span>
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function AgentDetailDrawer({
  agent,
  open,
  onClose,
  badge,
  workflowId,
  history,
  executions,
  decisions,
  loadingActivity,
}: {
  agent: AgentSpec | null;
  open: boolean;
  onClose: () => void;
  badge: string | null;
  workflowId: string;
  history: WorkflowHistoryEntry[];
  executions: AgentExecution[];
  decisions: AgentDecision[];
  loadingActivity: boolean;
}) {
  const drawerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onPointer = (e: MouseEvent) => {
      const target = e.target as Node | null;
      if (!target) return;
      if (drawerRef.current?.contains(target)) return;
      // Roster clicks switch agent; keep the panel open.
      if ((e.target as Element | null)?.closest?.(".wf-agent")) return;
      onClose();
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open, onClose]);

  if (!agent) return null;

  const agentHistory = history.filter(
    (h) => h.node.includes(agent.key) || h.node.startsWith(`${agent.key}.`)
  );
  const latestDecision = decisions[0] || null;
  const stageLabel =
    agent.stage || `${agent.number}. ${agent.name}`;

  return (
    <div className={open ? "agent-drawer-root open" : "agent-drawer-root"} aria-hidden={!open}>
      <aside
        ref={drawerRef}
        className="agent-drawer"
        role="dialog"
        aria-modal="false"
        aria-labelledby="agent-drawer-title"
      >
        <header className="agent-drawer-head">
          <div>
            <div className="agent-drawer-kicker">AGENT {agentId(agent)}</div>
            <h2 id="agent-drawer-title">{agent.name}</h2>
            <p>{agent.summary || agent.role}</p>
          </div>
          <button type="button" className="agent-drawer-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="agent-drawer-body">
          {badge ? <span className="agent-drawer-badge">{badge}</span> : null}

          <section>
            <h3>Definition</h3>
            <p>{agent.definition || agent.role}</p>
          </section>
          <section>
            <h3>Role</h3>
            <p>{agent.role}</p>
          </section>
          <section>
            <h3>Description</h3>
            <p>{agent.description || agent.execution_strategy}</p>
          </section>
          <section>
            <h3>Input</h3>
            <p>{agent.inputs}</p>
          </section>
          <section>
            <h3>Execution strategy</h3>
            <p>{agent.execution_strategy}</p>
          </section>
          <section>
            <h3>Output</h3>
            <p>{agent.outputs}</p>
          </section>
          <section>
            <h3>Tools and technology</h3>
            <p>{agent.stack}</p>
          </section>
          <section>
            <h3>Appears in these workflow stages</h3>
            <div className="agent-drawer-stages">
              <span className="agent-drawer-stage">{stageLabel}</span>
            </div>
          </section>

          <section>
            <h3>Live activity</h3>
            {loadingActivity ? (
              <p className="agent-drawer-muted">Loading agent activity…</p>
            ) : executions.length === 0 && agentHistory.length === 0 ? (
              <p className="agent-drawer-muted">
                No runs yet for this agent in the current session. Activity appears
                after the pipeline reaches this stage.
              </p>
            ) : (
              <ul className="agent-drawer-activity">
                {executions.slice(0, 5).map((ex) => (
                  <li key={ex.id}>
                    <strong>{ex.status}</strong>
                    <span>
                      {ex.node}
                      {ex.latency_ms != null ? ` · ${ex.latency_ms} ms` : ""}
                      {ex.created_at ? ` · ${formatWhen(ex.created_at)}` : ""}
                    </span>
                    {ex.error ? <em>{ex.error}</em> : null}
                  </li>
                ))}
                {executions.length === 0
                  ? agentHistory.slice(-5).reverse().map((h, i) => (
                      <li key={`${h.node}-${i}`}>
                        <strong>{h.status}</strong>
                        <span>
                          {h.node}
                          {h.at ? ` · ${formatWhen(h.at)}` : ""}
                          {h.next_action ? ` · next ${h.next_action}` : ""}
                        </span>
                      </li>
                    ))
                  : null}
              </ul>
            )}
          </section>

          <section>
            <h3>Decision record</h3>
            <p className="agent-drawer-muted">
              {latestDecision
                ? "Latest recorded decision for this agent."
                : "Schema used when this agent writes a decision trace."}
            </p>
            <DecisionRecord
              agent={agent}
              workflowId={workflowId}
              latest={latestDecision}
            />
          </section>
        </div>
      </aside>
    </div>
  );
}

function AgentRoster({
  agents,
  selectedAgent,
  onSelect,
  activeKeys,
}: {
  agents: AgentSpec[];
  selectedAgent: string;
  onSelect: (id: string) => void;
  activeKeys: string[];
}) {
  return (
    <div className="wf-roster-inner">
      <ol className="wf-roster-list">
        {agents.map((agent) => {
          const id = agentId(agent);
          const selected = selectedAgent === id;
          const lit = activeKeys.includes(agent.key);
          return (
            <li key={agent.key}>
              <button
                type="button"
                className={
                  selected ? "wf-agent selected" : lit ? "wf-agent lit" : "wf-agent"
                }
                onClick={() => onSelect(id)}
              >
                <span className="wf-agent-num">{id}</span>
                <span className="wf-agent-copy">
                  <strong>{agent.name}</strong>
                  <em>{agent.summary || agent.role}</em>
                </span>
                <span
                  className={selected || lit ? "wf-dot" : "wf-dot soft"}
                  aria-hidden
                />
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function WorkflowPage() {
  const router = useRouter();
  const [selectedList, setSelectedList] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadPreview, setUploadPreview] = useState<{
    rows_detected?: number;
    rows_invalid?: number;
    mapping?: Record<string, string>;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedAgent, setSelectedAgent] = useState("01");
  const [followPipelineAgent, setFollowPipelineAgent] = useState(true);
  const [detailAgentId, setDetailAgentId] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<AgentSpec[]>([]);
  const [agentExecutions, setAgentExecutions] = useState<AgentExecution[]>([]);
  const [agentDecisions, setAgentDecisions] = useState<AgentDecision[]>([]);
  const [loadingActivity, setLoadingActivity] = useState(false);
  const [botOpen, setBotOpen] = useState(true);
  const [botMinimized, setBotMinimized] = useState(true);
  const [connections, setConnections] = useState<SourceConnection[]>([]);
  const [connectorCatalog, setConnectorCatalog] = useState<Connector[]>([]);
  const [connectConfig, setConnectConfig] = useState<Record<string, string>>({});
  const [connectName, setConnectName] = useState("");
  const [connectBusy, setConnectBusy] = useState<"test" | "import" | "">("");
  const [connectNotice, setConnectNotice] = useState("");
  const [importMode, setImportMode] = useState<string>("");
  const [externalImportPhase, setExternalImportPhase] =
    useState<ExternalImportPhase>(null);
  const [pendingLiveImport, setPendingLiveImport] =
    useState<ConnectImportResult | null>(null);
  const [externalReviewList, setExternalReviewList] =
    useState<ProspectList | null>(null);
  const [externalSchema, setExternalSchema] = useState<FixturePreview | null>(null);
  const [externalSchemaBusy, setExternalSchemaBusy] = useState(false);
  const [ingestLogs, setIngestLogs] = useState<IngestLogLine[]>([]);
  const [ingestValidating, setIngestValidating] = useState(false);
  const [sampleOpen, setSampleOpen] = useState(false);
  const [sampleBusy, setSampleBusy] = useState(false);
  const [samplePreview, setSamplePreview] = useState<FixturePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [workflowDetail, setWorkflowDetail] = useState<WorkflowDetail | null>(null);
  const [run, setRun] = useState<RunState>({
    phase: "idle",
    workflowId: "",
    currentNode: "",
    pausedAt: null,
    openConflicts: 0,
    created: 0,
    leadIds: [],
    message: "",
  });

  const hydrateConnectForm = (
    key: string,
    catalogList: Connector[],
    conns: SourceConnection[]
  ) => {
    const connector = catalogList.find((c) => c.key === key);
    const existing = conns.find((c) => c.connector_key === key && c.is_enabled);
    const initial: Record<string, string> = {};
    (connector?.config_fields || []).forEach((field) => {
      const saved = existing?.config?.[field.name];
      if (saved != null && String(saved) !== "") {
        initial[field.name] = String(saved);
      } else if (field.default != null) {
        initial[field.name] = String(field.default);
      } else {
        initial[field.name] = "";
      }
    });
    setConnectConfig(initial);
    setConnectName(existing?.name || connector?.display_name || key);
    setConnectNotice("");
    setImportMode(existing?.status === "connected" ? "live" : "");
  };

  useEffect(() => {
    api
      .get<SourceConnection[]>("/sources/connections")
      .then(setConnections)
      .catch((e) => setError(e.message));
    api
      .get<AgentSpec[]>("/agents/catalog")
      .then(setCatalog)
      .catch((e) => setError(e.message));
    api
      .get<Connector[]>("/sources/catalog")
      .then(setConnectorCatalog)
      .catch((e) => setError(e.message));
  }, []);

  // If the user clicked a source before the catalog arrived, hydrate the form.
  useEffect(() => {
    if (
      selectedSource &&
      selectedSource !== "manual_upload" &&
      connectorCatalog.length > 0 &&
      Object.keys(connectConfig).length === 0
    ) {
      hydrateConnectForm(selectedSource, connectorCatalog, connections);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectorCatalog, selectedSource, connections]);

  const agents = useMemo(() => rosterAgents(catalog), [catalog]);

  const activeStep = useMemo(
    () => nodeToStep(run.currentNode, run.phase, run.pausedAt),
    [run.currentNode, run.phase, run.pausedAt]
  );

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const agent =
        params.get("agent") ||
        window.sessionStorage.getItem("leadsense.selectedAgent") ||
        "";
      if (/^\d{2}$/.test(agent)) {
        setSelectedAgent(agent);
        setFollowPipelineAgent(false);
        window.sessionStorage.removeItem("leadsense.selectedAgent");
      }
      const wf =
        params.get("workflow_id") ||
        window.sessionStorage.getItem("leadsense.workflowId") ||
        "";
      if (wf) {
        setRun((prev) => ({ ...prev, workflowId: wf }));
        void refreshWorkflow(wf).catch(() => {
          /* keep idle timeline */
        });
      }
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!followPipelineAgent) return;
    if (run.phase === "idle") return;
    setSelectedAgent(agentForPhase(activeStep, run.phase, run.currentNode));
  }, [activeStep, run.phase, run.currentNode, followPipelineAgent]);

  const selectRosterItem = (id: string) => {
    setFollowPipelineAgent(false);
    setSelectedAgent(id);
    setDetailAgentId(id);
  };

  const goToNextAgent = () => {
    setFollowPipelineAgent(false);
    const ids = agents.map((a) => agentId(a));
    const idx = ids.indexOf(selectedAgent);
    if (idx >= 0 && idx < ids.length - 1) {
      const next = ids[idx + 1];
      setSelectedAgent(next);
      setDetailAgentId(null);
      return;
    }
    router.push("/leads");
  };

  const detailAgent = useMemo(
    () => agents.find((a) => agentId(a) === detailAgentId) || null,
    [agents, detailAgentId]
  );

  useEffect(() => {
    if (!detailAgent) {
      setAgentExecutions([]);
      setAgentDecisions([]);
      return;
    }
    let cancelled = false;
    setLoadingActivity(true);
    const qs = new URLSearchParams({ agent: detailAgent.key, limit: "8" });
    if (run.workflowId) qs.set("workflow_id", run.workflowId);
    Promise.all([
      api.get<AgentExecution[]>(`/agents/executions?${qs}`),
      api.get<AgentDecision[]>(`/agents/decisions?${qs}`),
    ])
      .then(([execs, decs]) => {
        if (cancelled) return;
        setAgentExecutions(execs);
        setAgentDecisions(decs);
      })
      .catch(() => {
        if (cancelled) return;
        setAgentExecutions([]);
        setAgentDecisions([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingActivity(false);
      });
    return () => {
      cancelled = true;
    };
  }, [detailAgent, run.workflowId, run.phase, run.currentNode]);

  const detailBadge = useMemo(() => {
    if (!detailAgent) return null;
    return agentRuntimeBadge(detailAgent.key, run.phase, run.currentNode, busy);
  }, [detailAgent, run.phase, run.currentNode, busy]);

  const selectedDataset = useMemo(
    () => LISTS.find((list) => list.id === selectedList) || null,
    [selectedList]
  );

  const sampleColumns = useMemo(() => {
    if (!samplePreview?.headers?.length) return [] as string[];
    const preferred = [
      "full_name",
      "email",
      "title",
      "company_name",
      "location",
      "industry",
      "employee_count",
      "tech_stack",
    ];
    const rest = samplePreview.headers.filter((h) => !preferred.includes(h));
    return [...preferred.filter((h) => samplePreview.headers.includes(h)), ...rest];
  }, [samplePreview]);

  useEffect(() => {
    setSampleOpen(false);
    setSamplePreview(null);
    setSampleBusy(false);
  }, [selectedList]);

  const startExtractionDisplay = async () => {
    if (!selectedDataset) return;
    if (sampleOpen) {
      setSampleOpen(false);
      return;
    }
    setSampleBusy(true);
    setError("");
    try {
      const preview = await api.get<FixturePreview>(
        `/sources/fixtures/${encodeURIComponent(selectedDataset.file)}/preview?limit=50`
      );
      setSamplePreview(preview);
      setSampleOpen(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not load dataset");
      setSampleOpen(false);
      setSamplePreview(null);
    } finally {
      setSampleBusy(false);
    }
  };

  const activeKeys = useMemo(() => {
    const keys: string[] = [];
    if (run.phase !== "idle") {
      keys.push("ingestion", "supervisor");
    } else {
      keys.push("ingestion");
    }
    if (activeStep >= 3) keys.push("extraction");
    if (activeStep >= 4) keys.push("verification");
    if (activeStep >= 5 || run.phase === "completed") keys.push("enrichment");
    if (activeStep >= 6 || run.phase === "completed") keys.push("scoring");
    return keys;
  }, [activeStep, run.phase]);

  const refreshWorkflow = async (workflowId: string) => {
    const detail = await api.get<WorkflowDetail>(`/agents/workflows/${workflowId}`);
    setWorkflowDetail(detail);
    const pausedAt =
      detail.status === "paused"
        ? String(detail.state?.paused_at || detail.current_node || "verification")
        : null;
    const openConflicts = Number(detail.state?.open_conflicts || 0);
    const leadIds = Array.isArray(detail.state?.lead_ids)
      ? (detail.state.lead_ids as string[])
      : [];
    setRun((prev) => ({
      ...prev,
      workflowId,
      phase:
        detail.status === "paused"
          ? "paused"
          : detail.status === "completed"
            ? "completed"
            : "running",
      currentNode: detail.current_node,
      pausedAt,
      openConflicts,
      leadIds: leadIds.length ? leadIds : prev.leadIds,
      message:
        detail.status === "paused"
          ? `Pipeline paused at verification — ${openConflicts || "open"} conflict(s) need human review.`
          : detail.status === "completed"
            ? "Pipeline completed through enrichment and scoring."
            : `Workflow at ${detail.current_node}.`,
    }));
  };

  // Poll workflow state while running or paused so the checkpoint timeline updates.
  useEffect(() => {
    if (!run.workflowId) return;
    if (run.phase !== "running" && run.phase !== "paused") return;
    let cancelled = false;
    const tick = async () => {
      try {
        if (!cancelled) await refreshWorkflow(run.workflowId);
      } catch {
        /* keep last known timeline */
      }
    };
    const id = window.setInterval(tick, run.phase === "paused" ? 4000 : 1500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.workflowId, run.phase]);

  // Optimistic checkpoint animation while Continue is in flight (before workflow id exists).
  useEffect(() => {
    if (!busy || run.phase !== "running" || run.workflowId) return;
    const preview = ["ingestion", "pipeline.start", "extraction", "verification"];
    let i = 0;
    const stamp = () => new Date().toISOString();
    setWorkflowDetail({
      workflow_id: "pending",
      status: "running",
      current_node: preview[0],
      paused_reason: "",
      state: { next_action: "pipeline.start" },
      history: [{ node: preview[0], status: "running", at: stamp(), next_action: "pipeline.start" }],
    });
    const id = window.setInterval(() => {
      i += 1;
      if (i >= preview.length) {
        window.clearInterval(id);
        return;
      }
      const node = preview[i];
      setWorkflowDetail((prev) => ({
        workflow_id: prev?.workflow_id || "pending",
        status: "running",
        current_node: node,
        paused_reason: "",
        state: { next_action: preview[i + 1] || "human_review" },
        history: [
          ...(prev?.history || []),
          {
            node,
            status: "running",
            at: stamp(),
            next_action: preview[i + 1] || "human_review",
          },
        ],
      }));
    }, 420);
    return () => window.clearInterval(id);
  }, [busy, run.phase, run.workflowId]);

  const selectedConnector = useMemo(
    () =>
      selectedSource && selectedSource !== "manual_upload"
        ? connectorCatalog.find((c) => c.key === selectedSource) || null
        : null,
    [connectorCatalog, selectedSource]
  );

  const connectionForSource = useMemo(
    () =>
      selectedSource
        ? connections.find(
            (c) => c.connector_key === selectedSource && c.is_enabled
          ) || null
        : null,
    [connections, selectedSource]
  );

  const clearExternalImportFlow = () => {
    setExternalImportPhase(null);
    setPendingLiveImport(null);
    setExternalReviewList(null);
    setExternalSchema(null);
    setExternalSchemaBusy(false);
    setIngestLogs([]);
    setIngestValidating(false);
  };

  const selectSource = (key: string) => {
    setSelectedSource(key);
    setError("");
    setSelectedList(null);
    setConnectNotice("");
    setImportMode("");
    clearExternalImportFlow();
    if (key === "manual_upload") {
      setUploadFile(null);
      setUploadPreview(null);
      setConnectConfig({});
      window.setTimeout(() => fileInputRef.current?.click(), 0);
    } else {
      setUploadFile(null);
      setUploadPreview(null);
      hydrateConnectForm(key, connectorCatalog, connections);
    }
  };

  const beginExternalLiveReview = async (res: ConnectImportResult) => {
    const connectorKey = res.connector_key || selectedSource || "";
    const list = bfsiListForConnector(connectorKey);
    setPendingLiveImport(res);
    setExternalReviewList(list);
    setExternalImportPhase("review");
    setIngestLogs([]);
    setImportMode(res.mode);
    setConnectNotice(res.message);
    if (res.connection) {
      setConnections((prev) => {
        const others = prev.filter((c) => c.id !== res.connection!.id);
        return [...others, res.connection!];
      });
    }
    if (list) {
      setSelectedList(list.id);
      setExternalSchemaBusy(true);
      try {
        const preview = await api.get<FixturePreview>(
          `/sources/fixtures/${encodeURIComponent(list.file)}/preview?limit=8`
        );
        setExternalSchema(preview);
      } catch {
        setExternalSchema(null);
      } finally {
        setExternalSchemaBusy(false);
      }
    } else {
      setExternalSchema(null);
    }
  };

  const validateAndCreateIngestionJob = async () => {
    if (!pendingLiveImport?.sync || ingestValidating) return;
    const sync = pendingLiveImport.sync;
    const fileLabel = stagingFileLabel(
      externalReviewList,
      pendingLiveImport.connector_key || selectedSource || "source"
    );
    const tenantLabel = "TEN-001";
    const script = buildIngestLogScript(sync, fileLabel, tenantLabel);

    setIngestValidating(true);
    setExternalImportPhase("streaming");
    setIngestLogs([]);
    setError("");

    try {
      for (let i = 0; i < script.length; i += 1) {
        await new Promise((r) => window.setTimeout(r, i === 0 ? 280 : 420));
        setIngestLogs((prev) => [...prev, script[i]]);
      }
      await new Promise((r) => window.setTimeout(r, 500));
      setExternalImportPhase("results");
      await applyConnectResult(pendingLiveImport);
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Could not create ingestion job"
      );
      setExternalImportPhase("review");
    } finally {
      setIngestValidating(false);
    }
  };

  const applyConnectResult = async (res: ConnectImportResult) => {
    setImportMode(res.mode);
    setConnectNotice(res.message);
    if (res.connection) {
      setConnections((prev) => {
        const others = prev.filter((c) => c.id !== res.connection!.id);
        return [...others, res.connection!];
      });
    } else {
      try {
        const refreshed = await api.get<SourceConnection[]>("/sources/connections");
        setConnections(refreshed);
      } catch {
        /* keep local */
      }
    }

    const sync = res.sync;
    if (!sync?.workflow_id) return;

    const pausedAt = sync.paused_at || null;
    const openConflicts = sync.open_conflicts || 0;
    const created = sync.created;
    await refreshWorkflow(sync.workflow_id);
    try {
      window.sessionStorage.setItem("leadsense.workflowId", sync.workflow_id);
    } catch {
      /* ignore */
    }
    setRun((prev) => ({
      ...prev,
      created,
      message:
        pausedAt === "verification" || openConflicts > 0
          ? `Ingested ${created} leads (${res.mode}). Verification paused with ${openConflicts} conflict(s).`
          : `Connected via ${res.mode} import — ingested ${created} leads.`,
    }));
  };

  const runConnectAndImport = async (opts: {
    testOnly?: boolean;
    allowDemo?: boolean;
    limit?: number;
  }) => {
    if (!selectedSource || selectedSource === "manual_upload") return null;
    const res = await api.post<ConnectImportResult>(
      `/sources/connectors/${selectedSource}/connect-and-import`,
      {
        name: connectName || selectedConnector?.display_name || selectedSource,
        config: connectConfig,
        limit: opts.limit ?? 25,
        run_pipeline: !opts.testOnly,
        reset_cursor: false,
        test_only: Boolean(opts.testOnly),
        allow_demo: Boolean(opts.allowDemo),
        lawful_basis: selectedConnector?.requires_policy_review
          ? "legitimate_interest"
          : "legitimate_interest",
      }
    );
    return res;
  };

  const testExternalSource = async () => {
    if (!selectedSource || selectedSource === "manual_upload") return;
    setConnectBusy("test");
    setError("");
    setConnectNotice("");
    try {
      const res = await runConnectAndImport({ testOnly: true, allowDemo: false });
      if (!res) return;
      setImportMode(res.mode);
      setConnectNotice(res.message);
      if (res.connection) {
        setConnections((prev) => {
          const others = prev.filter((c) => c.id !== res.connection!.id);
          return [...others, res.connection!];
        });
      }
      if (!res.test?.ok) {
        setError(res.test?.message || res.message || "Connection test failed");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection test failed");
    } finally {
      setConnectBusy("");
    }
  };

  const connectAndImportLive = async () => {
    if (!selectedSource || selectedSource === "manual_upload") return;
    setConnectBusy("import");
    setBusy(true);
    setError("");
    setConnectNotice("");
    clearExternalImportFlow();
    try {
      const res = await runConnectAndImport({
        testOnly: false,
        allowDemo: false,
        limit: 50,
      });
      if (!res) return;
      if (res.mode === "needs_credentials") {
        setImportMode(res.mode);
        setConnectNotice(res.message);
        setError(res.message);
        return;
      }
      // Live external imports get the BFSI review → Validate → stream → results flow.
      // Demo / fallback paths keep the existing immediate apply behaviour.
      if (res.mode === "live" && res.sync) {
        await beginExternalLiveReview(res);
        return;
      }
      setRun((prev) => ({
        ...prev,
        phase: "running",
        message: `Connecting to ${selectedConnector?.display_name || selectedSource} and importing…`,
        currentNode: "ingestion",
        pausedAt: null,
        openConflicts: 0,
        workflowId: "",
      }));
      setWorkflowDetail(null);
      await applyConnectResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connect and import failed");
      clearExternalImportFlow();
      setRun((prev) => ({
        ...prev,
        phase: "idle",
        message: "",
        currentNode: "",
      }));
      setWorkflowDetail(null);
    } finally {
      setConnectBusy("");
      setBusy(false);
    }
  };

  const onPickUploadFile = async (file: File | null) => {
    setUploadFile(file);
    setUploadPreview(null);
    if (!file) return;
    setSelectedSource("manual_upload");
    setSelectedList("mu-tech");
    try {
      const form = new FormData();
      form.append("file", file);
      const preview = await api.upload<{
        rows_detected?: number;
        rows_invalid?: number;
        mapping?: Record<string, string>;
      }>("/sources/upload/preview", form);
      setUploadPreview(preview);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not preview upload");
    }
  };

  const continuePipeline = async (): Promise<boolean> => {
    const list = selectedList ? LISTS.find((item) => item.id === selectedList) : null;
    const sourceKey =
      selectedSource || list?.connector_key || null;
    if (!sourceKey) {
      setError("Select a source connector first.");
      return false;
    }
    if (sourceKey === "manual_upload" && !uploadFile && !list) {
      setError("Upload a local CSV/Excel file or choose an upload prospect list.");
      return false;
    }
    // External sources: prefer live connect-and-import. Demo lists only when
    // the user explicitly picked a canned list (or has no credentials yet).
    if (sourceKey !== "manual_upload") {
      const hasAnyConfig = Object.values(connectConfig).some(
        (v) => v != null && String(v).trim() !== "" && String(v) !== "********"
      );
      if (!hasAnyConfig && !list && importMode !== "live") {
        setError(
          "Enter live credentials and click Connect & Import, or pick a demo prospect list."
        );
        return false;
      }
    }

    setBusy(true);
    setError("");
    setRun((prev) => ({
      ...prev,
      phase: "running",
      message: "Agent 01 Ingestion validating and deduping leads…",
      currentNode: "ingestion",
      pausedAt: null,
      openConflicts: 0,
      workflowId: "",
    }));
    setWorkflowDetail(null);

    try {
      let workflowId = "";
      let pausedAt: string | null = null;
      let openConflicts = 0;
      let created = 0;

      if (sourceKey === "manual_upload") {
        const form = new FormData();
        if (uploadFile) {
          form.append("file", uploadFile, uploadFile.name);
          if (uploadPreview?.mapping) {
            form.append("mapping_json", JSON.stringify(uploadPreview.mapping));
          }
        } else {
          form.append("file", buildTechCsv(), list?.file || "saas_platform_targets.csv");
        }
        form.append("run_pipeline", "true");
        const res = await api.upload<UploadResult>("/sources/upload", form);
        workflowId = res.workflow_id;
        pausedAt = res.paused_at || null;
        openConflicts = res.open_conflicts || 0;
        created = res.rows_valid;
        if (res.lead_ids?.length) {
          setRun((prev) => ({ ...prev, leadIds: res.lead_ids }));
        }
      } else {
        const hasAnyConfig = Object.values(connectConfig).some(
          (v) => v != null && String(v).trim() !== "" && String(v) !== "********"
        );
        // Live first when credentials are present; otherwise demo list path.
        const res = await api.post<ConnectImportResult>(
          `/sources/connectors/${sourceKey}/connect-and-import`,
          {
            name: connectName || selectedConnector?.display_name || sourceKey,
            config: connectConfig,
            limit: list ? Math.min(list.rows, 50) : 25,
            run_pipeline: true,
            allow_demo: !hasAnyConfig || Boolean(list && !hasAnyConfig),
            lawful_basis: "legitimate_interest",
          }
        );
        setImportMode(res.mode);
        setConnectNotice(res.message);
        if (res.mode === "needs_credentials") {
          setError(res.message);
          setRun((prev) => ({
            ...prev,
            phase: "idle",
            message: "",
            currentNode: "",
          }));
          setWorkflowDetail(null);
          return false;
        }
        if (res.connection) {
          setConnections((prev) => {
            const others = prev.filter((c) => c.id !== res.connection!.id);
            return [...others, res.connection!];
          });
        }
        if (!res.sync) {
          setError(res.message || "Import did not return sync results");
          setRun((prev) => ({
            ...prev,
            phase: "idle",
            message: "",
            currentNode: "",
          }));
          return false;
        }
        workflowId = res.sync.workflow_id;
        pausedAt = res.sync.paused_at || null;
        openConflicts = res.sync.open_conflicts || 0;
        created = res.sync.created;
      }

      if (workflowId) {
        await refreshWorkflow(workflowId);
        setRun((prev) => ({
          ...prev,
          created,
          message:
            pausedAt === "verification" || openConflicts > 0
              ? `Ingested ${created} leads. Verification paused with ${openConflicts} conflict(s) — human review required.`
              : prev.message || `Ingested ${created} leads and advanced the pipeline.`,
        }));
      } else {
        setRun((prev) => ({
          ...prev,
          phase: "completed",
          created,
          message: `Ingested ${created} leads.`,
        }));
      }
      return true;
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Pipeline run failed";
      setError(message);
      setRun((prev) => ({ ...prev, phase: "error", message }));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const handleContinue = () => {
    // Agent 01: ingest selected fixture (canonical extract → verify), then open bench.
    if (selectedAgent === "01") {
      void (async () => {
        const list = selectedDataset;
        let wf = run.workflowId || workflowDetail?.workflow_id || "";

        if (list?.file) {
          setBusy(true);
          setError("");
          setRun((prev) => ({
            ...prev,
            phase: "running",
            message: `Running ${list.title} through extract → verify (canonical profiles)…`,
            currentNode: "extraction",
            pausedAt: null,
            openConflicts: 0,
          }));
          try {
            const qs = new URLSearchParams({
              filename: list.file,
              limit: String(Math.min(list.rows || 50, 50)),
              run_pipeline: "true",
              connector_key: list.connector_key || "manual_upload",
            });
            const res = await api.post<{
              workflow_id: string;
              open_conflicts?: number;
              paused_at?: string | null;
              rows_valid?: number;
              lead_ids?: string[];
              status?: string;
            }>(`/sources/fixtures/run?${qs.toString()}`, {});
            wf = res.workflow_id || "";
            const openConflicts = res.open_conflicts || 0;
            const pausedAt = res.paused_at || null;
            setRun((prev) => ({
              ...prev,
              workflowId: wf,
              leadIds: res.lead_ids || prev.leadIds,
              created: res.rows_valid ?? prev.created,
              openConflicts,
              pausedAt,
              phase:
                openConflicts > 0 || pausedAt === "verification"
                  ? "paused"
                  : "completed",
              currentNode: pausedAt || "verification",
              message:
                openConflicts > 0
                  ? `Pipeline paused — ${openConflicts} verification conflict(s) after canonical_profile.`
                  : "Fixture verified; opening Verification workbench.",
            }));
          } catch (e: unknown) {
            const message =
              e instanceof ApiError
                ? e.status === 404
                  ? "Verification run endpoint not found. Confirm the API on port 8000 is running the latest code."
                  : e.message
                : e instanceof Error
                  ? e.message
                  : "Could not run fixture for verification";
            setError(message);
            setRun((prev) => ({
              ...prev,
              phase: "error",
              message,
            }));
            setBusy(false);
            return;
          } finally {
            setBusy(false);
          }
        }

        if (!wf) {
          setError(
            "Select a prospect list (or Connect & Import) first, then open the Verification bench."
          );
          return;
        }

        setFollowPipelineAgent(false);
        setSelectedAgent("02");
        setDetailAgentId(null);
        try {
          window.sessionStorage.setItem("leadsense.workflowId", wf);
        } catch {
          /* ignore */
        }
        router.push(`/verification?workflow_id=${encodeURIComponent(wf)}`);
      })();
      return;
    }
    goToNextAgent();
  };

  const stage = (() => {
    if (selectedAgent === "01") {
      return {
        title: "Lead Ingestion",
        body: "Agent 01 accepts RawLead[] from seven source connectors, validates schema, dedupes on email or name|company, persists leads as ingested, and returns lead_ids + job stats. Watch the Orchestrator bot (bottom-right) for live checkpoints.",
      };
    }
    if (run.phase === "paused" || selectedAgent === "02") {
      return {
        title: "Verification",
        body: "Conflicts were found between uploaded and extracted values. The Orchestrator paused the workflow — enrichment and scoring stay blocked until a reviewer resolves each field.",
      };
    }
    if (run.phase === "completed" || selectedAgent === "04") {
      return {
        title: "ICP scoring",
        body: "Trusted leads were enriched and scored. Open Leads or Analytics to inspect bands, factors and evidence for this workflow.",
      };
    }
    if (selectedAgent === "03" || activeStep >= 5) {
      return {
        title: "Enrichment",
        body: "Verification cleared. Enrichment is normalizing titles, seniority and persona signals before scoring.",
      };
    }
    return {
      title: "Lead Ingestion",
      body: "Pick a prospect list or Connect & Import on Agent 01. Continue opens Verification next — extraction still runs automatically in the pipeline.",
    };
  })();

  return (
    <PortalShell
      hideJourney
      sidebar={
        <AgentRoster
          agents={agents}
          selectedAgent={selectedAgent}
          onSelect={selectRosterItem}
          activeKeys={activeKeys}
        />
      }
    >
      <div className="wf-stage-head">
        <div>
          <h1>{stage.title}</h1>
          <p>{stage.body}</p>
          {run.workflowId ? (
            <p className="small muted" style={{ marginTop: 8 }}>
              Workflow <span className="mono">{run.workflowId}</span>
              {run.currentNode ? ` · node ${run.currentNode}` : ""}
            </p>
          ) : null}
        </div>
      </div>

      {error ? <div className="notice error">{error}</div> : null}
      {run.message && run.phase !== "idle" ? (
        <div
          className={`notice ${
            run.phase === "paused"
              ? "info"
              : run.phase === "error"
                ? "error"
                : "success"
          }`}
        >
          {run.message}
          {run.phase === "paused" ? (
            <>
              {" "}
              <Link href="/verification">Open human review →</Link>
            </>
          ) : null}
          {run.phase === "completed" ? (
            <>
              {" "}
              <Link href="/leads">View leads →</Link>
            </>
          ) : null}
        </div>
      ) : null}

      {selectedAgent === "02" ? (
        <section className="wf-panel">
          <h2>Agent 02 · Verification (human gate)</h2>
          <p className="wf-panel-sub">
            Compares uploaded vs extracted title, company, location and email.
            MISMATCH / NEEDS_REVIEW pauses the Orchestrator; enrichment and scoring
            stay blocked until a reviewer resolves each field.
          </p>
          <p className="hint" style={{ marginBottom: 0 }}>
            Run Connect &amp; Import on Agent 01 to produce conflicts, then open{" "}
            <Link href="/verification">Verification</Link>. Click the Orchestrator
            pill to review live agent checkpoints.
          </p>
        </section>
      ) : selectedAgent === "03" ? (
        <section className="wf-panel">
          <h2>Agent 03 · Enrichment</h2>
          <p className="wf-panel-sub">
            Runs only after Verification is clear. Infers seniority, function,
            persona and attaches firmographic / technographic signals from the
            trusted profile.
          </p>
          <ul className="wf-supervisor-flow">
            <li>Skips leads with open conflicts</li>
            <li>Normalised title → seniority / persona / skills</li>
            <li>Industry, headcount, tech stack from extraction</li>
          </ul>
          {run.phase === "completed" || activeStep >= 5 ? (
            <p className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
              Enrichment complete for this workflow.{" "}
              <Link href="/leads">Inspect leads →</Link>
            </p>
          ) : (
            <p className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
              Clear the verification queue to unlock enrichment.
            </p>
          )}
        </section>
      ) : selectedAgent === "04" ? (
        <section className="wf-panel">
          <h2>Agent 04 · ICP &amp; Lead Scoring</h2>
          <p className="wf-panel-sub">
            Weighted ICP score (0–100) with HOT / HIGH / MEDIUM / LOW bands and
            factor evidence. Requires an enrichment row first.
          </p>
          {(() => {
            const scoring = workflowDetail?.state?.scoring as
              | { bands?: Record<string, number>; items?: { band: string; score: number }[] }
              | undefined;
            const bands = scoring?.bands;
            if (bands && Object.keys(bands).length) {
              return (
                <div className="wf-connectors" style={{ marginTop: 8 }}>
                  {Object.entries(bands).map(([band, count]) => (
                    <span key={band} className="wf-connector-chip">
                      {band}: {count}
                    </span>
                  ))}
                </div>
              );
            }
            return (
              <p className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
                {run.phase === "completed"
                  ? "Scoring finished — open Leads or Analytics for factor detail."
                  : "Scoring runs after enrichment on the same workflow_id."}
              </p>
            );
          })()}
          <p className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
            <Link href="/leads">View scored leads</Link>
            {" · "}
            <Link href="/dashboard">Dashboard</Link>
          </p>
        </section>
      ) : (
        <section className="wf-panel">
          <h2>Agent 01 · Source connectors → RawLead[]</h2>
          <p className="wf-panel-sub">
            Click a source to open its live connection form. Enter vendor credentials
            (or a CSV/S3 URL), then Test or Connect &amp; Import to pull real data.
            Demo prospect lists remain available as a fallback. Manual Upload still
            uses a local file picker.
          </p>
          <div className="wf-connectors">
            {SOURCE_CONNECTORS.map((c) => {
              const conn = connections.find(
                (row) => row.connector_key === c.key && row.is_enabled
              );
              const live =
                c.key !== "manual_upload" &&
                conn?.status === "connected" &&
                Boolean(
                  conn.config &&
                    Object.values(conn.config).some(
                      (v) => v != null && String(v) !== "" && String(v) !== "********"
                    )
                );
              return (
                <button
                  key={c.key}
                  type="button"
                  className={
                    selectedSource === c.key
                      ? "wf-connector-chip selected"
                      : "wf-connector-chip"
                  }
                  onClick={() => selectSource(c.key)}
                  disabled={busy || Boolean(connectBusy)}
                  title={
                    c.key === "manual_upload"
                      ? "Upload a CSV or Excel file from your computer"
                      : live
                        ? "Live credentials connected — re-open to sync again"
                        : "Open live connection form for this source"
                  }
                >
                  {c.label}
                  {c.key !== "manual_upload" && live ? (
                    <em className="wf-connector-live">live</em>
                  ) : null}
                </button>
              );
            })}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.tsv,.xlsx,.xls"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              void onPickUploadFile(f);
              e.target.value = "";
            }}
          />

          {selectedSource === "manual_upload" ? (
            <div className="wf-upload-panel">
              <div className="wf-upload-row">
                <div>
                  <strong>Local file upload</strong>
                  <p>
                    {uploadFile
                      ? `${uploadFile.name}${
                          uploadPreview?.rows_detected != null
                            ? ` · ${uploadPreview.rows_detected} rows detected`
                            : ""
                        }`
                      : "Choose a CSV or Excel file, or pick the Technology buyers demo list below."}
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {uploadFile ? "Replace file" : "Browse files"}
                </button>
              </div>
              {uploadPreview?.mapping ? (
                <div className="wf-upload-map">
                  {Object.entries(uploadPreview.mapping).map(([field, column]) => (
                    <span key={field}>
                      <strong>{field}</strong> ← {column}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {selectedConnector ? (
            <div className="wf-connect-panel">
              <div className="wf-connect-panel-head">
                <div>
                  <strong>Connect {selectedConnector.display_name}</strong>
                  <p>
                    {selectedConnector.description} Credentials are saved on your
                    tenant connection and used for live fetch — not the demo CSVs.
                  </p>
                </div>
                {importMode ? (
                  <span
                    className={
                      importMode === "live"
                        ? "badge ok"
                        : importMode === "demo"
                          ? "badge medium"
                          : "badge neutral"
                    }
                  >
                    {importMode}
                  </span>
                ) : connectionForSource?.status ? (
                  <span className="badge neutral">{connectionForSource.status}</span>
                ) : null}
              </div>
              <div className="wf-connect-fields">
                <label className="wf-connect-field">
                  <span>Connection name</span>
                  <input
                    value={connectName}
                    onChange={(e) => setConnectName(e.target.value)}
                    disabled={busy || Boolean(connectBusy)}
                  />
                </label>
                {selectedConnector.config_fields.map((field) => (
                  <label className="wf-connect-field" key={field.name}>
                    <span>
                      {field.label}
                      {field.required ? " *" : ""}
                    </span>
                    {field.type === "select" ? (
                      <select
                        value={connectConfig[field.name] || ""}
                        onChange={(e) =>
                          setConnectConfig((prev) => ({
                            ...prev,
                            [field.name]: e.target.value,
                          }))
                        }
                        disabled={busy || Boolean(connectBusy)}
                      >
                        <option value="">Select…</option>
                        {(field.options || []).map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : field.type === "boolean" ? (
                      <select
                        value={connectConfig[field.name] || "true"}
                        onChange={(e) =>
                          setConnectConfig((prev) => ({
                            ...prev,
                            [field.name]: e.target.value,
                          }))
                        }
                        disabled={busy || Boolean(connectBusy)}
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : (
                      <input
                        type={field.secret || field.type === "password" ? "password" : "text"}
                        value={connectConfig[field.name] || ""}
                        placeholder={field.help || ""}
                        onChange={(e) =>
                          setConnectConfig((prev) => ({
                            ...prev,
                            [field.name]: e.target.value,
                          }))
                        }
                        disabled={busy || Boolean(connectBusy)}
                        autoComplete="off"
                      />
                    )}
                    {field.help ? <em>{field.help}</em> : null}
                  </label>
                ))}
              </div>
              <div className="wf-connect-actions">
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || Boolean(connectBusy)}
                  onClick={() => void testExternalSource()}
                >
                  {connectBusy === "test" ? "Testing…" : "Test connection"}
                </button>
                <button
                  type="button"
                  disabled={busy || Boolean(connectBusy)}
                  onClick={() => void connectAndImportLive()}
                >
                  {connectBusy === "import" ? "Importing…" : "Connect & Import"}
                </button>
              </div>
              {connectNotice ? (
                <p className="wf-connect-notice">{connectNotice}</p>
              ) : null}
            </div>
          ) : null}

          {externalImportPhase && pendingLiveImport?.sync ? (
            <div className="wf-external-ingest">
              {externalImportPhase === "review" ? (
                <>
                  <h3 className="wf-subhead">Staged external dataset</h3>
                  <p className="hint" style={{ marginTop: 0, marginBottom: 10 }}>
                    Live import from{" "}
                    <strong>
                      {selectedConnector?.display_name ||
                        pendingLiveImport.connector_key}
                    </strong>{" "}
                    is ready. Review the BFSI prospect list and schema, then
                    validate to create the ingestion job.
                  </p>
                  {externalReviewList ? (
                    <div className="wf-list-card selected wf-external-list-card">
                      <strong>{externalReviewList.title}</strong>
                      <span className="wf-list-desc">
                        {externalReviewList.description}
                      </span>
                      <span className="wf-list-meta">
                        <span className="wf-list-tags">
                          <span className="badge medium">
                            {externalReviewList.connector_key}
                          </span>
                          <span className="badge neutral">
                            {externalReviewList.industry}
                          </span>
                          <span className="badge ok">live import</span>
                        </span>
                        <span
                          className="wf-list-file mono"
                          title={externalReviewList.file}
                        >
                          {stagingFileLabel(
                            externalReviewList,
                            pendingLiveImport.connector_key
                          )}
                        </span>
                      </span>
                    </div>
                  ) : null}

                  <div className="wf-dataset-preview" style={{ marginTop: 12 }}>
                    <div className="wf-dataset-preview-head">
                      <div>
                        <strong>Schema details</strong>
                        <p>
                          Required RawLead fields and sample columns from the
                          staged BFSI extract.
                        </p>
                      </div>
                      <span className="badge agent">
                        {pendingLiveImport.sync.fetched} fetched
                      </span>
                    </div>
                    <div className="wf-dataset-preview-grid">
                      <span>
                        <strong>Source file</strong>
                        <em className="mono">
                          {stagingFileLabel(
                            externalReviewList,
                            pendingLiveImport.connector_key
                          )}
                        </em>
                      </span>
                      <span>
                        <strong>Rows staged</strong>
                        <em>{pendingLiveImport.sync.fetched} observations</em>
                      </span>
                      <span>
                        <strong>Industry</strong>
                        <em>{externalReviewList?.industry || "BFSI"}</em>
                      </span>
                      <span>
                        <strong>Job</strong>
                        <em className="mono">
                          {pendingLiveImport.sync.job_id || "pending"}
                        </em>
                      </span>
                      <span>
                        <strong>Fields</strong>
                        <em>
                          {externalSchemaBusy
                            ? "Loading schema…"
                            : externalSchema?.headers?.length
                              ? externalSchema.headers.join(", ")
                              : "external_id, full_name, email, title, company_name, location, industry, employee_count"}
                        </em>
                      </span>
                      <span>
                        <strong>Required</strong>
                        <em>
                          full_name, email, title, company_name, location,
                          industry
                        </em>
                      </span>
                    </div>
                    {externalSchema?.sample_rows?.length ? (
                      <div className="wf-sample-panel" style={{ marginTop: 10 }}>
                        <p className="hint" style={{ marginTop: 0 }}>
                          Sample rows ({externalSchema.sample_count} of{" "}
                          {externalSchema.rows_total})
                        </p>
                        <div className="wf-sample-table-wrap">
                          <table className="wf-sample-table">
                            <thead>
                              <tr>
                                {(externalSchema.headers || [])
                                  .slice(0, 6)
                                  .map((h) => (
                                    <th key={h}>{h}</th>
                                  ))}
                              </tr>
                            </thead>
                            <tbody>
                              {externalSchema.sample_rows.slice(0, 5).map((row, idx) => (
                                <tr key={idx}>
                                  {(externalSchema.headers || [])
                                    .slice(0, 6)
                                    .map((h) => (
                                      <td key={h}>{row[h] || "—"}</td>
                                    ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="wf-connect-actions" style={{ marginTop: 14 }}>
                    <button
                      type="button"
                      disabled={ingestValidating || busy}
                      onClick={() => void validateAndCreateIngestionJob()}
                    >
                      Validate &amp; Create Ingestion Job
                    </button>
                  </div>
                </>
              ) : null}

              {externalImportPhase === "streaming" ||
              (externalImportPhase === "results" && ingestLogs.length) ? (
                <div className="wf-ingest-job">
                  <div className="wf-ingest-job-head">
                    <h3>Ingestion job</h3>
                    <p className="mono">
                      job_id: {pendingLiveImport.sync.job_id || "JOB-pending"}{" "}
                      | tenant: TEN-001
                    </p>
                  </div>
                  <div className="wf-ingest-console" aria-live="polite">
                    {ingestLogs.map((line, idx) => (
                      <div
                        key={`${line.at}-${idx}`}
                        className={`wf-ingest-line level-${line.level}`}
                      >
                        <span className="wf-ingest-ts">{line.at}</span>
                        <span className="wf-ingest-msg">{line.text}</span>
                      </div>
                    ))}
                    {externalImportPhase === "streaming" ? (
                      <div className="wf-ingest-line level-info">
                        <span className="wf-ingest-ts">…</span>
                        <span className="wf-ingest-msg">Processing…</span>
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {externalImportPhase === "results" ? (
                <div className="wf-ingest-results">
                  <div className="wf-ingest-stat">
                    <span>Rows read</span>
                    <strong>{pendingLiveImport.sync.fetched}</strong>
                    <em>
                      from{" "}
                      {stagingFileLabel(
                        externalReviewList,
                        pendingLiveImport.connector_key
                      )}
                    </em>
                  </div>
                  <div className="wf-ingest-stat ok">
                    <span>Valid records</span>
                    <strong>{pendingLiveImport.sync.created}</strong>
                    <em>queued for extraction</em>
                  </div>
                  <div className="wf-ingest-stat warn">
                    <span>Duplicates collapsed</span>
                    <strong>{pendingLiveImport.sync.duplicates}</strong>
                    <em>email + company key</em>
                  </div>
                  <div className="wf-ingest-stat err">
                    <span>Quarantined</span>
                    <strong>{pendingLiveImport.sync.invalid}</strong>
                    <em>failed syntax validation</em>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          <h3 className="wf-subhead">
            {selectedSource
              ? selectedSource === "manual_upload"
                ? "Or choose an upload prospect list (by industry)"
                : "Optional demo prospect lists (fallback)"
              : "Choose a prospect list"}
          </h3>
          <p className="hint" style={{ marginTop: 0, marginBottom: 10 }}>
            {selectedSource && selectedSource !== "manual_upload"
              ? "Use these only when you want fixture data instead of a live vendor pull. Live Connect & Import does not need a list."
              : "A source system can feed many prospect lists across industries. Pick the audience slice, then Continue."}
          </p>
          <div className="wf-lists">
            {LISTS.filter(
              (list) => !selectedSource || list.connector_key === selectedSource
            ).map((list) => (
              <button
                key={list.id}
                type="button"
                className={
                  selectedList === list.id
                    ? "wf-list-card selected"
                    : "wf-list-card"
                }
                onClick={() => {
                  clearExternalImportFlow();
                  setSelectedList(list.id);
                  setSelectedSource(list.connector_key);
                  if (list.connector_key !== "manual_upload") {
                    setUploadFile(null);
                    setUploadPreview(null);
                    hydrateConnectForm(
                      list.connector_key,
                      connectorCatalog,
                      connections
                    );
                  }
                }}
                disabled={busy || Boolean(connectBusy) || ingestValidating}
              >
                <strong>{list.title}</strong>
                <span className="wf-list-desc">{list.description}</span>
                <span className="wf-list-meta">
                  <span className="wf-list-tags">
                    <span className="badge medium">{list.connector_key}</span>
                    <span className="badge neutral">{list.industry}</span>
                  </span>
                  <span className="wf-list-file mono" title={list.file}>
                    {list.file}
                  </span>
                </span>
              </button>
            ))}
          </div>
          {selectedDataset ? (
            <div className="wf-dataset-preview">
              <div className="wf-dataset-preview-head">
                <div>
                  <strong>{selectedDataset.title}</strong>
                  <p>{selectedDataset.description}</p>
                </div>
                <div className="wf-dataset-preview-actions">
                  <span className="badge agent">{selectedDataset.connector_key}</span>
                </div>
              </div>
              <div className="wf-dataset-preview-grid">
                <span>
                  <strong>File</strong>
                  <em className="mono">{selectedDataset.file}</em>
                </span>
                <span>
                  <strong>Rows</strong>
                  <em>{selectedDataset.rows} observations</em>
                </span>
                <span>
                  <strong>Industry</strong>
                  <em>{selectedDataset.industry}</em>
                </span>
                <span>
                  <strong>Coverage</strong>
                  <em>{selectedDataset.coverage}</em>
                </span>
                <span>
                  <strong>Regions</strong>
                  <em>{selectedDataset.regions}</em>
                </span>
                <span>
                  <strong>Fields</strong>
                  <em>
                    {samplePreview?.headers?.length
                      ? samplePreview.headers.join(", ")
                      : "external_id, full_name, first_name, last_name, email, title, company_name, location, profile_url, phone, industry, employee_count, tech_stack, segment, source_hint, notes"}
                  </em>
                </span>
              </div>

              <div className="wf-connect-actions" style={{ marginTop: 14 }}>
                <button
                  type="button"
                  disabled={busy || sampleBusy}
                  onClick={() => void startExtractionDisplay()}
                >
                  {sampleBusy
                    ? "Loading…"
                    : sampleOpen
                      ? "Hide dataset"
                      : "Start Extraction"}
                </button>
              </div>

              {sampleOpen && samplePreview ? (
                <div className="wf-sample-panel">
                  <div className="wf-sample-panel-head">
                    <strong>Dataset</strong>
                    <span className="hint">
                      Showing {samplePreview.sample_count} of{" "}
                      {samplePreview.rows_total || selectedDataset.rows} rows from{" "}
                      <span className="mono">{samplePreview.filename}</span>
                    </span>
                  </div>
                  <div className="wf-sample-table-wrap">
                    <table className="wf-sample-table">
                      <thead>
                        <tr>
                          {sampleColumns.map((col) => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {samplePreview.sample_rows.map((row, idx) => (
                          <tr key={`${samplePreview.filename}-${idx}`}>
                            {sampleColumns.map((col) => (
                              <td key={col} title={row[col] || ""}>
                                {row[col] || "—"}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              <p className="hint" style={{ marginTop: 10, marginBottom: 0 }}>
                Demo-only fixture shaped like a real source export. Prefer Connect
                &amp; Import above when you have vendor credentials.
              </p>
            </div>
          ) : null}
          {selectedSource &&
          selectedSource !== "manual_upload" &&
          !selectedConnector ? (
            <p className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
              Loading connector form for <span className="mono">{selectedSource}</span>
              …
            </p>
          ) : null}
        </section>
      )}

      <div className="wf-footer">
        <div className="wf-info">
          {run.phase === "paused"
            ? "Pipeline paused for human review. Resolve conflicts on Verification, or Continue to the next agent."
            : selectedAgent === "01"
              ? "Select a prospect list, then Open the Verification bench — the fixture runs extract → verify with canonical_profile so mismatches appear."
              : selectedAgent === "02"
                ? "Resolve conflicts on Verification, or Continue to Enrichment."
                : "Continue opens the next agent in the roster (or Leads after the last agent). Use Connect & Import on Agent 01 to run ingestion."}
        </div>
        {run.phase === "paused" && selectedAgent === "02" ? (
          <Link className="wf-continue" href="/verification" style={{ textAlign: "center" }}>
            Review conflicts
          </Link>
        ) : (
          <button
            type="button"
            className="wf-continue"
            disabled={busy}
            onClick={handleContinue}
          >
            {selectedAgent === "01" ? "Open the Verification bench" : "Continue"}
          </button>
        )}
      </div>

      <AgentDetailDrawer
        agent={detailAgent}
        open={Boolean(detailAgentId)}
        onClose={() => setDetailAgentId(null)}
        badge={detailBadge}
        workflowId={run.workflowId || workflowDetail?.workflow_id || ""}
        history={workflowDetail?.history || []}
        executions={agentExecutions}
        decisions={agentDecisions}
        loadingActivity={loadingActivity}
      />
      <OrchestratorBot
        open={botOpen}
        minimized={botMinimized}
        onOpen={() => {
          // Only the Orchestrator pill expands the bot panel.
          setBotOpen(true);
          setBotMinimized(false);
        }}
        onClose={() => {
          // Dock to pill — never fully remove the bot from the canvas.
          setBotOpen(true);
          setBotMinimized(true);
        }}
        onMinimize={() => {
          setBotOpen(true);
          setBotMinimized(true);
        }}
        history={workflowDetail?.history || []}
        currentNode={run.currentNode || workflowDetail?.current_node || ""}
        status={workflowDetail?.status || run.phase}
        pausedReason={
          workflowDetail?.paused_reason ||
          (run.phase === "paused"
            ? `${run.openConflicts} conflict(s) awaiting human review`
            : "")
        }
        nextAction={String(workflowDetail?.state?.next_action || "")}
        live={run.phase === "running" || busy || run.phase === "paused"}
        phase={run.phase}
        workflowId={run.workflowId || workflowDetail?.workflow_id || ""}
        openConflicts={run.openConflicts}
        created={run.created}
        busy={busy}
        onResume={async () => {
          if (!run.workflowId) return;
          setBusy(true);
          try {
            await api.post(`/agents/workflows/${run.workflowId}/resume`);
            await refreshWorkflow(run.workflowId);
          } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Resume failed");
          } finally {
            setBusy(false);
          }
        }}
      />
    </PortalShell>
  );
}
