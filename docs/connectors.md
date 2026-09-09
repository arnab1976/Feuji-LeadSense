# Adding a source connector

Every lead source in LeadSense is a subclass of `SourceConnector`. The platform
never talks to a vendor SDK directly, which is why a new source is one file and
one import rather than a change that ripples through the codebase.

## The five steps

### 1. Create the module

`backend/app/connectors/pipedrive.py`

```python
from app.connectors.base import (
    Capability, ConfigField, ConnectorKind, FetchResult, RawLead, SourceConnector,
)
from app.connectors.registry import register_connector
from app.core.errors import ConnectorError
import httpx


@register_connector
class PipedriveConnector(SourceConnector):
    key = "pipedrive"                     # unique, used in the database
    display_name = "Pipedrive"
    description = "Sync persons from a Pipedrive pipeline."
    kind = ConnectorKind.CRM
    capabilities = {Capability.FETCH, Capability.INCREMENTAL, Capability.PUSH}
    requires_policy_review = False        # True for data vendors and web sources
```

### 2. Declare the settings form

The portal renders this automatically. Nothing in the frontend needs editing.

```python
    config_fields = [
        ConfigField("api_token", "API token", "password",
                    required=True, secret=True),
        ConfigField("pipeline_id", "Pipeline id", "text",
                    help="Optional. Restrict the sync to one pipeline."),
    ]
```

`secret=True` means the value is masked on read and a masked value submitted back
is ignored instead of overwriting the stored one.

### 3. Say when credentials exist

This drives `demo_mode`, which is what lets a fresh clone run without any keys.

```python
    def has_credentials(self) -> bool:
        return bool(self.config.get("api_token"))
```

### 4. Implement `test_connection` and `fetch`

```python
    def test_connection(self) -> dict:
        if self.demo_mode:
            return {"ok": True, "message": "Demo mode", "details": {"demo": True}}
        with httpx.Client(timeout=30) as client:
            r = client.get("https://api.pipedrive.com/v1/users/me",
                           params={"api_token": self.config["api_token"]})
        return {"ok": r.status_code < 400, "message": f"HTTP {r.status_code}",
                "details": {}}

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        if self.demo_mode:
            from app.connectors.demo_data import demo_leads
            return FetchResult(leads=demo_leads(self.key, limit),
                               warnings=["demo mode — no token configured"])

        with httpx.Client(timeout=60) as client:
            r = client.get("https://api.pipedrive.com/v1/persons",
                           params={"api_token": self.config["api_token"],
                                   "start": int(cursor or 0), "limit": limit})
        if r.status_code >= 400:
            raise ConnectorError(f"Pipedrive fetch failed: {r.text[:300]}")

        payload = r.json()
        leads = [
            RawLead(
                external_id=str(p["id"]),
                full_name=p.get("name", ""),
                email=(p.get("primary_email") or "").lower(),
                title=p.get("job_title", ""),
                company_name=(p.get("org_id") or {}).get("name", ""),
                source=f"{self.key}:person",
                raw=p,                    # keep the untouched payload
            )
            for p in payload.get("data") or []
        ]
        more = payload.get("additional_data", {}).get("pagination", {})
        return FetchResult(leads=leads,
                           cursor=str(more.get("next_start", "")),
                           has_more=bool(more.get("more_items_in_collection")))
```

### 5. Register the import

In `backend/app/connectors/__init__.py`:

```python
from app.connectors import pipedrive  # noqa: F401,E402
```

That is the whole job. The connector now appears in the catalog endpoint, renders
its own settings form in the portal, is syncable from the UI and by the hourly
beat task, and flows into the same ingestion, verification, enrichment and
scoring pipeline as every other source.

---

## Contract reference

### `RawLead`

The single shape every connector produces.

| Field | Notes |
|---|---|
| `external_id` | The source's own identifier |
| `full_name`, `email`, `title`, `company_name` | Core fields |
| `location`, `profile_url`, `phone` | Optional |
| `industry`, `employee_count`, `tech_stack` | Feed the scoring factors |
| `source` | Free text, e.g. `"salesforce:Lead"` |
| `raw` | The untouched vendor payload — never drop this |

`dedupe_key()` prefers the lower-cased email, falling back to
name + company. `is_valid()` rejects records with neither a name nor an email,
and malformed addresses.

Keep `raw` populated. It means a mapping can be re-run later without re-fetching,
and it is what an auditor asks for.

### `FetchResult`

`leads`, `cursor` (opaque, stored on the connection for the next incremental
sync), `has_more`, `warnings` (surfaced in the sync response).

### Optional methods

- `push(records)` — write-back. Salesforce creates Tasks, HubSpot creates note
  engagements. Raise `ConnectorError` if unsupported; the base class does this.
- `enrich(lead)` — attributes for one known record, used by data vendors.
- `parse(content, filename, mapping)` — file connectors only; see
  `ManualUploadConnector` for the fuzzy header detection.

---

## Demo mode

```python
@property
def demo_mode(self) -> bool:
    return settings.demo_connectors and not self.has_credentials()
```

When `DEMO_CONNECTORS=true` and no credentials are configured, connectors return
synthetic records from `demo_data.py`. Support it in `fetch` and
`test_connection` — it is what makes the repository demonstrable on a laptop with
no accounts, and what keeps the test suite free of network calls.

`demo_data.demo_leads(source, limit, offset)` takes an offset so different
sources yield different people. Without it, dedupe correctly collapses the second
source into nothing and the demo silently shows one source instead of two.

---

## Policy-gated sources

Set `requires_policy_review = True` for data vendors and anything scraped. Three
things then follow automatically:

1. `POST /sources/connections` forces `policy_allowed = False` when no lawful
   basis is supplied, regardless of what the request asked for.
2. The extraction agent refuses those leads and marks them `policy_blocked`.
3. The compliance agent fails `source_policy` and `lawful_basis` — both hard
   blocks — so the approval endpoint returns HTTP 409.

`WebProfileConnector` goes further and raises `PolicyViolation` for any host
outside the tenant allow-list *before* a request is made. Source terms of service
are the top adoption risk for this category of product, so the guard belongs in
the connector, not in a review step further downstream.

---

## Testing a new connector

Add to `backend/tests/test_connectors.py`:

```python
def test_pipedrive_demo_mode():
    connector = build_connector("pipedrive", {})
    assert connector.demo_mode is True
    assert len(connector.fetch(limit=5).leads) == 5
    assert connector.test_connection()["ok"] is True
```

The existing `test_every_connector_is_registered` and
`test_catalog_exposes_a_config_form` will cover the registration and the form
without any change.
