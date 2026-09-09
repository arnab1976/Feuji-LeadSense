# API reference

Base path `/api/v1`. Interactive docs at `/docs` when the server is running.

All endpoints except `/auth/dev-token` and `/health` require
`Authorization: Bearer <token>` and are scoped to the token's tenant.

## Auth

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/auth/dev-token` | — | Dev mode only; disabled when `AUTH_MODE=entra` |
| GET | `/auth/me` | any | Identity, role and resolved permissions |

## Sources

| Method | Path | Permission |
|---|---|---|
| GET | `/sources/catalog` | any |
| GET | `/sources/connections` | any |
| POST | `/sources/connections` | `source:manage` |
| PATCH | `/sources/connections/{id}` | `source:manage` |
| DELETE | `/sources/connections/{id}` | `source:manage` |
| POST | `/sources/connections/{id}/test` | `source:manage` |
| POST | `/sources/connections/{id}/sync` | `lead:write` |
| POST | `/sources/upload/preview` | `lead:write` |
| POST | `/sources/upload` | `lead:write` |

`/sources/catalog` returns each connector's `config_fields`, which is what the
portal renders as a settings form. Add a connector and it appears here with no
frontend change.

`/sources/upload/preview` parses without persisting, so a user confirms the
detected column mapping before anything is ingested. Both upload endpoints accept
`multipart/form-data`; `upload` also takes `mapping_json` and `run_pipeline`.

Sync and upload return counts split into created, duplicate and invalid, plus
`open_conflicts` when the pipeline paused at verification.

## Leads

| Method | Path | Permission |
|---|---|---|
| GET | `/leads` | `lead:read` |
| GET | `/leads/stats` | `lead:read` |
| GET | `/leads/{id}` | `lead:read` |
| GET | `/leads/verification/queue` | `lead:read` |
| POST | `/leads/verification/resolve` | `lead:write` |
| POST | `/leads/verification/bulk-resolve` | `lead:write` |
| POST | `/leads/enrich` | `lead:write` |
| POST | `/leads/score` | `lead:write` |
| POST | `/leads/segments/preview` | `lead:read` |
| POST | `/leads/segments` | `campaign:write` |
| GET | `/leads/segments/list` | `lead:read` |
| GET | `/leads/segments/{id}/members` | `lead:read` |

`GET /leads` filters on `status`, `band`, `connector_key`, `min_score`.

`GET /leads/{id}` returns the whole decision trail: the uploaded record, the
extraction, every verification row with its method and confidence, the
enrichment, and the score with per-factor value, weight, contribution and
evidence.

`POST /leads/score` accepts a `weights` object and does **not** persist it — put
weights on tenant policy if you want them shared.

`POST /leads/segments/preview` runs segmentation and rolls the transaction back,
so a user can iterate on thresholds without creating anything.

## Knowledge

| Method | Path | Permission |
|---|---|---|
| GET | `/knowledge/documents` | any |
| POST | `/knowledge/documents` | `campaign:write` |
| POST | `/knowledge/documents/{id}/approve` | `campaign:write` |
| GET | `/knowledge/search?q=&k=` | any |

Approval is the control that decides what agents may cite. Retrieval filters on
`approved = true`, so an unapproved document is invisible rather than merely
deprioritised.

## Campaigns and emails

| Method | Path | Permission |
|---|---|---|
| GET/POST | `/campaigns` | `campaign:read` / `campaign:write` |
| GET | `/campaigns/{id}` | `campaign:read` |
| POST | `/campaigns/{id}/strategy` | `campaign:write` |
| POST | `/campaigns/{id}/emails` | `campaign:write` |
| GET | `/emails` | `campaign:read` |
| GET | `/emails/{id}` | `campaign:read` |
| PATCH | `/emails/{id}` | `campaign:write` |
| POST | `/emails/approve` | `email:approve` |
| POST | `/emails/send` | `email:approve` |

`POST /campaigns/{id}/emails` generates drafts **and** runs the compliance gate,
returning both results. Generation without a compliance verdict is not a state
the API will produce.

`PATCH /emails/{id}` re-runs compliance, because an edited body has not been
checked. The edit is recorded as `edited_by_human` rather than hidden — edit rate
is a quality metric.

`POST /emails/approve` returns **409 `policy_violation`** if any email carries a
`BLOCK` verdict, with the failed check keys in `detail.blocked`. A reviewer cannot
approve past compliance.

`POST /emails/send` only sends emails with a recorded approval; anything else is
counted as `skipped`.

## Replies

| Method | Path | Permission |
|---|---|---|
| GET | `/replies` | `campaign:read` |
| POST | `/replies` | `campaign:write` |
| POST | `/replies/{id}/execute` | `campaign:write` |
| POST | `/replies/{id}/reject` | `campaign:write` |

Intents: `MEETING_REQUEST`, `INFORMATION_REQUEST`, `NOT_NOW`, `UNSUBSCRIBE`,
`REFERRAL`, `NEGATIVE`, `UNCLEAR`. Each carries a confidence, a score delta
applied to the lead, a proposed next action and a CRM payload routed back to the
connector the lead came from.

`UNSUBSCRIBE` executes immediately with no human gate — it is a legal obligation,
not a recommendation. Everything else with `requires_human` waits for
`/execute`.

## Analytics and agents

| Method | Path |
|---|---|
| GET | `/analytics/dashboard` |
| GET | `/analytics/campaigns/{id}` |
| GET | `/analytics/costs` |
| GET | `/agents/catalog` |
| GET | `/agents/executions` |
| GET | `/agents/decisions` |
| GET | `/agents/workflows` |
| GET | `/agents/workflows/{id}` |
| GET | `/agents/audit` |

`/analytics/costs` aggregates tokens, spend and average latency per agent and
divides by emails generated — cost per email, instrumented from the first build
because unit economics decide whether this scales.

`/agents/decisions` carries `human_override`, which is how a human correction is
distinguished from an agent's own judgement.

## Tenants

| Method | Path | Permission |
|---|---|---|
| GET | `/tenants` | any |
| GET | `/tenants/policy` | any |
| PUT | `/tenants/policy` | `policy:manage` |
| GET | `/tenants/suppression` | any |
| POST | `/tenants/suppression` | `policy:manage` |

## Errors

```json
{ "error": "policy_violation", "message": "…", "detail": { } }
```

| Code | HTTP |
|---|---|
| `not_found` | 404 |
| `permission_denied` | 403 |
| `policy_violation` | 409 |
| `validation_failed` | 422 |
| `connector_error` | 502 |

## Roles

`platform_admin`, `tenant_admin`, `sales_manager`, `campaign_manager`,
`sales_executive`, `reviewer`, `analyst`, `read_only`.

The matrix lives in `backend/app/core/security.py`. Extend it there rather than
adding role checks to routers.
