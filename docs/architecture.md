# Architecture

## Why it is shaped this way

Three constraints drove nearly every decision:

1. **The verification step is the product.** Anything that lets an unverified
   value reach a prospect is a defect, so verification is a hard gate in the
   orchestration graph rather than a screen a user can skip.
2. **An enterprise buyer audits controls, not features.** Every action that could
   embarrass a customer — extracting from a source, contacting a person,
   citing a claim — has one place where it is allowed or refused.
3. **It has to run before it has credentials.** A demo that needs six API keys and
   a Postgres cluster does not get demonstrated. Every external dependency has a
   local fallback.

---

## Request path

```
Next.js page
  → lib/api.ts            attaches the bearer token
  → FastAPI router        RBAC via Depends(require_permission(...))
  → agent(s)              via AgentContext (db, tenant, workflow, user)
  → services              llm / rag / policy / scoring / email
  → SQLAlchemy models     every row carries tenant_id
```

Routers own the transaction. Agents never commit, so a failed node leaves no
half-written state and can be retried.

---

## Orchestration

`app/orchestration/graph.py` declares the pipeline once, as an ordered list of
nodes with two kinds of conditional:

- `gate` — should this node run at all, given the current state
- `pauses_when` — should the workflow stop here and wait for a human

```python
PIPELINE = [
    NodeSpec("extraction",   "extraction"),
    NodeSpec("verification", "verification",
             pauses_when=lambda s: s["open_conflicts"] > 0),
    NodeSpec("enrichment",   "enrichment",
             gate=lambda s: s["open_conflicts"] == 0),
    NodeSpec("scoring",      "scoring",
             gate=lambda s: s["open_conflicts"] == 0),
]
```

`LeadPipeline` executes this sequentially and writes a `WorkflowState` checkpoint
after every node. `build_langgraph_app()` compiles the same list into a LangGraph
`StateGraph` for native checkpointing, streaming and interrupts.

The sequential runner is not a placeholder. It keeps the repository installable
with one `pip install`, and it makes the gate logic unit-testable without a graph
runtime. Behaviour does not diverge because both paths call the same agents.

### State

`app/orchestration/state.py` defines `LeadSenseState`, a TypedDict that LangGraph
can use directly as its schema. Checkpoints persist to `workflow_states` with a
bounded history, so the Agent Monitor can show where a workflow is and why it
stopped.

---

## The agent contract

```python
class BaseAgent:
    key, name, role, inputs, execution_strategy, outputs, stack, version

    def execute(self, ctx: AgentContext, **kwargs) -> AgentResult: ...
    def run(self, ctx, **kwargs) -> AgentResult:   # instrumented wrapper
```

`run()` times the call, writes an `AgentExecution` row (latency, tokens, cost,
model, status) and an `AgentDecision` row (decision, confidence, reason,
evidence, rule or model version). Failures are recorded before they propagate.

That instrumentation is why three questions have answers:

- *Why was this lead scored 82?* — the decision row plus per-factor evidence.
- *What does a campaign cost us?* — `/analytics/costs`, aggregated per agent.
- *Who changed this?* — `human_override` on the decision, `resolved_by` on the
  record, plus an `audit_logs` entry.

### Deployment shape

Thirteen agent classes, not thirteen microservices. For production the
architecture document groups them into ten services along their real scaling
boundaries — extraction and delivery are I/O bound and bursty, verification and
scoring are CPU bound and steady. Nothing in the code assumes a single process:
agents communicate through the database and the Celery queues, so splitting them
out is a deployment change.

---

## Verification: three tiers, cheapest first

```
exact / rule           →  identical, or equivalent after expanding
                          abbreviations and stripping legal suffixes
fuzzy (RapidFuzz)      →  token_sort_ratio above the tenant threshold
semantic (embeddings)  →  cosine similarity for genuinely ambiguous pairs
```

Between the match and review thresholds a field becomes `NEEDS_REVIEW`; below,
`MISMATCH`. Both hold the lead. Cost stays proportional to difficulty — most
fields resolve at tier one for free.

Two normalisation details that were bugs before they were features:

- Punctuation is stripped **before** abbreviation expansion, otherwise
  `"Sr. Mgr, Risk"` becomes `"Senior. Manager Risk"` and `mgr` never expands.
- Title comparison removes filler words, so `VP Engineering` matches
  `Vice President of Engineering` while `VP Operations` still does **not** match
  `Vice President - Banking Operations`. The second genuinely needs a human.

---

## Scoring

Seven weighted factors, each returning a 0-100 value plus the evidence behind it:

| Factor | Default weight |
|---|---|
| ICP fit | 30 |
| Seniority | 20 |
| Industry fit | 15 |
| Company size | 10 |
| Technology fit | 10 |
| Engagement | 10 |
| Historical conversion | 5 |

Rules rather than a learned model, because a score a sales team cannot argue with
is a score they will not use. To add a propensity model, compute it in
`score_lead` and blend it as an eighth weighted factor — keep the rule factors so
the explanation survives.

Re-scoring through `POST /leads/score` with custom weights does **not** persist
them. Exploring in the UI must not change what a colleague sees.

---

## RAG and grounding

Only documents with `approved=True` are retrievable. That single predicate in
`services/rag.py` is what prevents the email agent inventing claims: an
unapproved document is not merely deprioritised, it is invisible.

Chunking is section-aware (split on blank lines, pack to ~700 characters).
Embeddings come from the configured provider, or a deterministic hashed
bag-of-words vector offline — not a semantic model, but stable and real enough to
exercise ranking end to end.

`groundedness` is derived from the best matching chunk and travels with the
generated email, where the compliance agent uses it as a quality check.

To move to pgvector: swap the `embedding` JSON column for `Vector(1536)`, add an
ivfflat index, and replace the Python cosine ranking with
`ORDER BY embedding <=> :query_vector`. Nothing above that line changes.

---

## Multi-tenancy

`tenant_id` on every tenant-scoped row, resolved from the token, applied in every
query. The shared-database model keeps the demo simple and is tested
(`test_tenant_isolation`).

For production, PostgreSQL Row-Level Security gives defence in depth without
touching the models — the column it needs is already there.

---

## Data model

~30 tables. The ones that carry the design:

- `leads` holds the **uploaded** record. `lead_extractions` holds the
  **extracted** view. They are separate rows on purpose: verification needs both,
  and overwriting one destroys the audit trail.
- `lead_verifications` is one row per compared field, with status, confidence,
  method, reason, and who resolved it.
- `agent_executions` / `agent_decisions` / `workflow_states` make agent behaviour
  queryable after the fact.
- `source_connections` carries `policy_allowed` and `lawful_basis`; the
  compliance agent reads them per lead.
- `suppression_entries` is checked before every send and written on unsubscribe
  and on hard bounce.

---

## Async work

Celery with three queues: `default`, `extraction`, `delivery`. A beat schedule
polls every enabled, policy-allowed connection hourly.

`CELERY_TASK_ALWAYS_EAGER=true` runs tasks inline so the API works without a
broker. Set it false, start a worker, and nothing else changes.

---

## Security

- **Identity**: Entra ID (OIDC, JWKS validated) or locally signed dev tokens.
- **Authorisation**: one permission matrix in `core/security.py`, eight roles.
  Routers declare `Depends(require_permission("email:approve"))` rather than
  scattering role checks.
- **Secrets**: connector secrets are masked on read (`********`) and a masked
  value submitted back is ignored rather than overwriting the stored one.
- **Source allow-listing**: `web_profile` raises `PolicyViolation` for any host
  outside the tenant allow-list, before a request is made.
