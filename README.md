# LeadSense

Agentic AI lead intelligence and sales engagement platform. Turns raw prospect
records into **verified, enriched, scored and actionable** sales intelligence,
with a human gate on every material action.

The distinguishing idea is not the email generation. It is that every lead is
reconciled against its source *before* anyone contacts it, and the pipeline stops
until a person resolves whatever did not reconcile.

---

## Quickstart (no infrastructure required)

A fresh clone runs the entire product offline: SQLite instead of Postgres, a
deterministic local generator instead of a hosted LLM, console output instead of
SES, and synthetic records from every connector that has no credentials.

```bash
git clone <your-remote> leadsense && cd leadsense
cp .env.example .env

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.db.seed          # creates the schema and loads demo data
uvicorn app.main:app --reload  # http://localhost:8000/docs

# Frontend (second terminal)
cd frontend
npm install
npm run dev                    # http://localhost:3000
```

Sign in with any of the seeded roles. `tenant_admin` sees everything;
`analyst` will be refused at the approval step, which is the point.

Or run the whole stack with Postgres, pgvector, Redis and a Celery worker:

```bash
docker compose up --build
```

### Make targets

| Command | What it does |
|---|---|
| `make install` | Install backend and frontend dependencies |
| `make seed` | Create tables and load demo data |
| `make api` | Run the API on :8000 |
| `make web` | Run the frontend on :3000 |
| `make worker` | Run the Celery worker |
| `make test` | Run the backend test suite |
| `make up` / `make down` | Full docker-compose stack |

---

## The five-minute demo path

1. **Sources** — look at the connector catalog. Seven connectors, each rendering
   its own settings form. Note that Apollo is marked *policy review* and its
   seeded connection is **blocked** with no lawful basis recorded.
2. **Sync** a source, or drop a CSV into manual upload. Columns are detected and
   shown before anything is ingested.
3. **Verification** — the pipeline has paused here. Uploaded values on the left,
   extracted on the right, with a confidence and a stated reason. `VP Ops` versus
   `Vice President Operations` was auto-matched; `VP Operations` versus
   `Vice President - Banking Operations` was not, and waits for you.
4. **Leads** — run enrichment and scoring. Move the weight sliders and re-score.
   Open a lead to see each factor's value, weight, contribution and evidence.
5. **Segments → Campaigns** — build a segment, plan a strategy grounded in the
   approved knowledge corpus, generate drafts. Note the unapproved competitor
   document cannot be selected.
6. **Email studio** — compliance verdicts per draft with six named checks. Edit a
   draft and the checks re-run, because an edited body has not been checked.
   Approve, then send.
7. **Analytics** — funnel, per-agent cost and latency, and reply classification.
   Paste "Please remove me from this list" and watch the contact land on the
   suppression list without asking anyone.
8. **Agents** — the 13 agents, the workflow checkpoints and the decision trace.

---

## Architecture at a glance

```
frontend/  Next.js 14 App Router, TypeScript, plain CSS
   │  fetch → /api/v1
backend/
   ├── api/v1/        11 routers  (auth, sources, leads, knowledge,
   │                               campaigns, emails, replies, analytics,
   │                               agents, tenants)
   ├── agents/        13 agents, each instrumented
   ├── orchestration/ pipeline with conditional gates + LangGraph adapter
   ├── connectors/    the pluggable source layer
   ├── services/      llm, rag, embeddings, scoring, taxonomy, policy,
   │                  email delivery, storage, telemetry
   ├── models/        ~30 tables, tenant_id on every row
   └── workers/       Celery tasks and beat schedule
```

Detail in [`docs/architecture.md`](docs/architecture.md).

### The thirteen agents

| # | Agent | Responsibility |
|---|---|---|
| 01 | Supervisor | Workflow state, checkpoints, retries, human gates |
| 02 | Lead Ingestion | Receives and validates bulk lead information |
| 03 | Extraction | Pulls the canonical profile from approved sources |
| 04 | **Verification** | Reconciles uploaded against extracted values |
| 05 | Enrichment | Normalises title, seniority, function, persona, skills |
| 06 | ICP & Scoring | Weighted, explainable 0-100 relevance score |
| 07 | Segmentation | Groups leads into viable audiences |
| 08 | Campaign Strategy | Objective into a grounded campaign plan |
| 09 | Email Generation | Personalised copy with provenance |
| 10 | Compliance & Quality | Six checks; four are hard blocks |
| 11 | Campaign Execution | Throttled sending via SES |
| 12 | Engagement Intelligence | Funnel, segment and variant performance |
| 13 | Reply + Next Best Action | Intent, score change, governed follow-up |

---

## Source connector layer

Every source implements one interface, so a spreadsheet, a CRM and a data vendor
arrive in the same shape and pass through the same policy checks.

| Connector | Kind | Capabilities |
|---|---|---|
| `manual_upload` | file | CSV/XLSX with fuzzy column detection |
| `csv_url` | file | HTTPS or S3 scheduled export |
| `salesforce` | crm | SOQL read, Task write-back, incremental cursor |
| `hubspot` | crm | v3 contacts, note engagements, pagination |
| `apollo` | enrichment | People search and match — *policy review* |
| `zoominfo` | enrichment | Skeleton showing the fourth-vendor pattern |
| `web_profile` | web | Allow-listed pages only — *policy review* |

Adding one is a single file. See [`docs/connectors.md`](docs/connectors.md).

---

## Configuration

Everything is environment driven; see `.env.example` for the full surface.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | SQLite file | Point at Postgres for pgvector |
| `AUTH_MODE` | `dev` | `entra` validates against Entra ID JWKS |
| `LLM_PROVIDER` | `echo` | `anthropic`, `openai`, `azure_openai` |
| `EMAIL_PROVIDER` | `console` | `ses` for real sending |
| `DEMO_CONNECTORS` | `true` | Synthetic data when credentials are absent |
| `CELERY_TASK_ALWAYS_EAGER` | `true` | Set false and run a worker |
| `ENABLE_PGVECTOR` | `false` | Creates the extension on startup |

Switching any of these is a config change, not a code change. That is deliberate:
the swap from demo to production should not be a rewrite.

---

## Where the controls are

Four things can stop an outbound message, and all of them are enforced server
side rather than in the UI:

1. **Source policy** — a disabled or disallowed source blocks extraction and
   outreach for every lead that came from it.
2. **Lawful basis** — a connector flagged for policy review starts blocked until
   a tenant admin records a basis.
3. **Suppression** — an unsubscribe is executed immediately, without a human gate,
   because it is a legal obligation rather than a recommendation.
4. **Compliance verdict** — a `BLOCK` makes the approval endpoint return HTTP 409.
   A reviewer cannot approve past it.

Everything a human decides is attributed: `resolved_by` on a verification,
`approver_name` on an approval, `human_override` on a decision, and an
`audit_logs` row for each.

---

## Tests

```bash
cd backend && pytest -q     # 33 tests
cd frontend && npm run typecheck && npm run build
```

The API suite walks the full product story through HTTP: upload → verify →
enrich → score → segment → campaign → generate → compliance → approve → send →
analytics → reply → next best action, and asserts that tenant isolation holds,
that a blocked email cannot be approved, and that a read-only role is refused.

---

## Production notes

This repository is an honest working system, not a production deployment. Before
it carries real prospect data:

- Replace `AUTH_MODE=dev` with Entra ID and remove the `/auth/dev-token` route.
- Move connector secrets from `config_json` to AWS Secrets Manager and store
  references only.
- Switch to Postgres with Row-Level Security or schema-per-tenant; `tenant_id` is
  already on every row and every query is scoped, but RLS gives defence in depth.
- Generate Alembic migrations instead of `create_all` (see `backend/alembic/`).
- Replace `ExtractionAgent._extract` with your real source fetch.
- Put a real rate limiter in front of `CampaignExecutionAgent`; the current
  throttle is recorded but not enforced across processes.
