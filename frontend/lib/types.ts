export type Connector = {
  key: string;
  display_name: string;
  description: string;
  kind: string;
  capabilities: string[];
  requires_policy_review: boolean;
  config_fields: ConfigField[];
};

export type ConfigField = {
  name: string;
  label: string;
  type: string;
  required: boolean;
  help: string;
  default: unknown;
  options: string[];
  secret: boolean;
};

export type SourceConnection = {
  id: string;
  name: string;
  connector_key: string;
  kind: string;
  status: string;
  is_enabled: boolean;
  policy_allowed: boolean;
  lawful_basis: string;
  last_sync_at: string | null;
  last_error: string;
  config: Record<string, unknown>;
};

export type Lead = {
  id: string;
  full_name: string;
  email: string;
  title: string;
  company_name: string;
  location: string;
  connector_key: string;
  status: string;
  score: number | null;
  band: string | null;
  persona: string | null;
  seniority: string | null;
  verification_status: string | null;
};

export type Conflict = {
  verification_id: string;
  lead_id: string;
  lead_name: string;
  company: string;
  field: string;
  uploaded_value: string;
  extracted_value: string;
  status: string;
  confidence: number;
  reason: string;
  method: string;
  resolved_value?: string;
  resolved_source?: string;
  resolved_by?: string;
  workflow_id?: string;
};

export type VerificationWorkbench = {
  workflow_id: string;
  stats: {
    match: number;
    mismatch: number;
    needs_review: number;
    resolved: number;
    open: number;
    total: number;
  };
  items: Conflict[];
};

export type Campaign = {
  id: string;
  name: string;
  objective: string;
  tone: string;
  segment_id: string | null;
  status: string;
  strategy: Record<string, any>;
  email_count: number;
};

export type GeneratedEmail = {
  id: string;
  lead_id: string;
  lead_name: string;
  lead_email: string;
  subject_variants: string[];
  selected_variant: number;
  body: string;
  groundedness: number;
  grounding: { title: string; score: number }[];
  tokens: number;
  cost_usd: number;
  edited_by_human: boolean;
  status: string;
  compliance: {
    verdict: string;
    risk_score: number;
    checks: { key: string; label: string; pass: boolean; reason: string }[];
  } | null;
};

export type AgentSpec = {
  number: number;
  key: string;
  name: string;
  role: string;
  summary?: string;
  definition?: string;
  description?: string;
  inputs: string;
  execution_strategy: string;
  outputs: string;
  stack: string;
  stage?: string;
  version?: string;
  kind?: "agent" | "orchestrator";
};

export type AgentExecution = {
  id: string;
  workflow_id: string;
  agent: string;
  node: string;
  status: string;
  latency_ms: number;
  tokens: number;
  cost_usd: number;
  model: string;
  error: string;
  created_at: string | null;
};

export type AgentDecision = {
  id: string;
  workflow_id: string;
  agent: string;
  decision: string;
  confidence: number;
  reason: string;
  entity_type: string;
  entity_id: string;
  model_or_rule_version: string;
  human_override: boolean;
  created_at: string | null;
};

export type SyncResult = {
  job_id: string;
  connector_key: string;
  fetched: number;
  created: number;
  duplicates: number;
  invalid: number;
  cursor: string;
  warnings: string[];
  workflow_id: string;
  paused_at?: string | null;
  open_conflicts: number;
};

export type ConnectImportResult = {
  connector_key: string;
  mode: "live" | "demo" | "needs_credentials" | "test_only" | string;
  connection: SourceConnection | null;
  test: { ok?: boolean; message?: string; details?: Record<string, unknown> };
  sync: SyncResult | null;
  message: string;
  config_fields: ConfigField[];
};

export type FixturePreview = {
  filename: string;
  headers: string[];
  rows_total: number;
  sample_rows: Record<string, string>[];
  sample_count: number;
};

export type UploadResult = {
  job_id: string;
  workflow_id: string;
  rows_read: number;
  rows_valid: number;
  rows_invalid: number;
  rows_duplicate: number;
  errors: unknown[];
  lead_ids: string[];
  mapping: Record<string, string>;
  paused_at?: string | null;
  open_conflicts: number;
};

export type WorkflowHistoryEntry = {
  node: string;
  status: string;
  at?: string;
  next_action?: string;
  keys?: string[];
};

export type WorkflowDetail = {
  workflow_id: string;
  status: string;
  current_node: string;
  paused_reason: string;
  state: Record<string, unknown>;
  history: WorkflowHistoryEntry[];
};
