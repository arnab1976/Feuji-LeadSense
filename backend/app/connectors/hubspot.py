"""HubSpot connector.

Reads CRM contacts through the v3 API using a private-app access token and can
write engagements back. Company attributes are pulled from the contact's
associated company when available.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.connectors.base import (
    Capability, ConfigField, ConnectorKind, FetchResult, RawLead, SourceConnector,
)
from app.connectors.registry import register_connector
from app.core.config import settings
from app.core.errors import ConnectorError

BASE = "https://api.hubapi.com"
CONTACT_PROPERTIES = [
    "firstname", "lastname", "email", "jobtitle", "company", "phone",
    "city", "country", "website", "industry", "numberofemployees",
    "hs_lead_status", "lastmodifieddate",
]


@register_connector
class HubSpotConnector(SourceConnector):
    key = "hubspot"
    display_name = "HubSpot"
    description = "Sync CRM contacts from HubSpot and log engagements back."
    kind = ConnectorKind.CRM
    capabilities = {Capability.FETCH, Capability.PUSH, Capability.INCREMENTAL,
                    Capability.SEARCH, Capability.WEBHOOK}
    config_fields = [
        ConfigField("access_token", "Private app token", "password", required=True, secret=True,
                    help="Scopes needed: crm.objects.contacts.read (and .write for push)."),
        ConfigField("list_id", "Contact list id", "text",
                    help="Optional. Restrict the sync to one HubSpot list."),
        ConfigField("lifecycle_stage", "Lifecycle stage filter", "text",
                    help="Optional, e.g. 'lead' or 'marketingqualifiedlead'."),
    ]

    def has_credentials(self) -> bool:
        return bool(self.config.get("access_token") or settings.hubspot_access_token)

    def _headers(self) -> dict:
        token = self.setting("access_token", "hubspot_access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_connection(self) -> dict:
        if self.demo_mode:
            return {"ok": True, "message": "Demo mode — synthetic HubSpot contacts",
                    "details": {"demo": True}}
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(f"{BASE}/crm/v3/objects/contacts",
                                  params={"limit": 1}, headers=self._headers())
            ok = resp.status_code < 400
            return {"ok": ok, "message": f"HTTP {resp.status_code}",
                    "details": {"body": resp.text[:200]} if not ok else {}}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "details": {}}

    @staticmethod
    def _to_lead(rec: dict[str, Any]) -> RawLead:
        p = rec.get("properties", {}) or {}
        name = " ".join(x for x in [p.get("firstname"), p.get("lastname")] if x)
        location = ", ".join(x for x in [p.get("city"), p.get("country")] if x)
        try:
            headcount = int(float(p.get("numberofemployees") or 0))
        except (TypeError, ValueError):
            headcount = 0
        return RawLead(
            external_id=str(rec.get("id", "")),
            full_name=name.strip(),
            email=(p.get("email") or "").lower(),
            title=p.get("jobtitle") or "",
            company_name=p.get("company") or "",
            location=location,
            profile_url=p.get("website") or "",
            phone=p.get("phone") or "",
            industry=p.get("industry") or "",
            employee_count=headcount,
            source="hubspot:contact",
            raw=rec,
        )

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        if self.demo_mode:
            from app.connectors.demo_data import demo_leads
            return FetchResult(leads=demo_leads("hubspot", limit),
                               warnings=["demo mode — no HubSpot token configured"])
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "properties": ",".join(CONTACT_PROPERTIES),
        }
        if cursor:
            params["after"] = cursor
        url = f"{BASE}/crm/v3/objects/contacts"
        if self.config.get("list_id"):
            url = f"{BASE}/crm/v3/lists/{self.config['list_id']}/memberships"
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, params=params, headers=self._headers())
        if resp.status_code >= 400:
            raise ConnectorError(f"HubSpot fetch failed: {resp.text[:300]}")
        payload = resp.json()
        leads = [self._to_lead(r) for r in payload.get("results", [])]
        after = (payload.get("paging", {}).get("next", {}) or {}).get("after", "")
        return FetchResult(leads=leads, cursor=after, has_more=bool(after))

    def push(self, records) -> dict:
        """Log a note engagement against each contact."""
        if self.demo_mode:
            items = list(records)
            return {"created": len(items), "demo": True}
        created = 0
        with httpx.Client(timeout=60) as client:
            for rec in records:
                body = {
                    "properties": {
                        "hs_note_body": rec.get("description", "LeadSense follow-up"),
                        "hs_timestamp": rec.get("timestamp"),
                    },
                    "associations": [{
                        "to": {"id": rec.get("external_id")},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED",
                                   "associationTypeId": 202}],
                    }] if rec.get("external_id") else [],
                }
                resp = client.post(f"{BASE}/crm/v3/objects/notes", json=body,
                                   headers=self._headers())
                if resp.status_code >= 400:
                    raise ConnectorError(f"HubSpot note failed: {resp.text[:300]}")
                created += 1
        return {"created": created}
