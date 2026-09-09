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
  inputs: string;
  execution_strategy: string;
  outputs: string;
  stack: string;
};
