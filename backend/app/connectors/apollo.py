"""Apollo.io connector.

Two jobs: search for new people matching an ICP, and enrich a record LeadSense
already holds. Apollo is a data vendor, so it is flagged
``requires_policy_review`` — the Compliance agent will not approve outreach to a
record sourced here until a lawful basis is recorded against the connection.
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


@register_connector
class ApolloConnector(SourceConnector):
    key = "apollo"
    display_name = "Apollo.io"
    description = "Prospect search and contact enrichment from Apollo."
    kind = ConnectorKind.ENRICHMENT
    capabilities = {Capability.FETCH, Capability.SEARCH, Capability.ENRICH,
                    Capability.INCREMENTAL}
    requires_policy_review = True
    config_fields = [
        ConfigField("api_key", "API key", "password", required=True, secret=True),
        ConfigField("person_titles", "Target titles", "text",
                    help="Comma separated, e.g. VP Operations, Head of Data"),
        ConfigField("organization_industries", "Industries", "text",
                    help="Comma separated, e.g. banking, insurance"),
        ConfigField("employee_ranges", "Employee ranges", "text", default="201,10000",
                    help="min,max"),
        ConfigField("locations", "Locations", "text",
                    help="Comma separated, e.g. India, United Kingdom"),
    ]

    def has_credentials(self) -> bool:
        return bool(self.config.get("api_key") or settings.apollo_api_key)

    @property
    def _base(self) -> str:
        return (self.config.get("base_url") or settings.apollo_base_url).rstrip("/")

    def _key(self) -> str:
        return self.setting("api_key", "apollo_api_key")

    def test_connection(self) -> dict:
        if self.demo_mode:
            return {"ok": True, "message": "Demo mode — synthetic Apollo results",
                    "details": {"demo": True}}
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(f"{self._base}/auth/health",
                                   json={"api_key": self._key()})
            return {"ok": resp.status_code < 400, "message": f"HTTP {resp.status_code}",
                    "details": {}}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "details": {}}

    @staticmethod
    def _csv(value: str | None) -> list[str]:
        return [v.strip() for v in (value or "").split(",") if v.strip()]

    @staticmethod
    def _to_lead(rec: dict[str, Any]) -> RawLead:
        org = rec.get("organization") or {}
        location = ", ".join(x for x in [rec.get("city"), rec.get("country")] if x)
        return RawLead(
            external_id=rec.get("id", ""),
            full_name=rec.get("name") or " ".join(
                x for x in [rec.get("first_name"), rec.get("last_name")] if x
            ),
            email=(rec.get("email") or "").lower(),
            title=rec.get("title") or "",
            company_name=org.get("name", ""),
            location=location,
            profile_url=rec.get("linkedin_url") or org.get("website_url") or "",
            phone=rec.get("phone_number") or "",
            industry=org.get("industry", ""),
            employee_count=int(org.get("estimated_num_employees") or 0),
            tech_stack=org.get("technology_names", [])[:12],
            source="apollo:person",
            raw=rec,
        )

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        if self.demo_mode:
            from app.connectors.demo_data import demo_leads
            return FetchResult(leads=demo_leads("apollo", limit),
                               warnings=["demo mode — no Apollo API key configured"])
        ranges = self._csv(self.config.get("employee_ranges") or "201,10000")
        body = {
            "api_key": self._key(),
            "page": int(cursor or 1),
            "per_page": min(limit, 100),
            "person_titles": self._csv(self.config.get("person_titles")),
            "organization_industry_tag_ids": self._csv(
                self.config.get("organization_industries")),
            "person_locations": self._csv(self.config.get("locations")),
            "organization_num_employees_ranges": ["-".join(ranges)] if len(ranges) == 2 else [],
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{self._base}/mixed_people/search", json=body)
        if resp.status_code >= 400:
            raise ConnectorError(f"Apollo search failed: {resp.text[:300]}")
        payload = resp.json()
        leads = [self._to_lead(p) for p in payload.get("people", [])]
        page = int(payload.get("pagination", {}).get("page", 1))
        total_pages = int(payload.get("pagination", {}).get("total_pages", 1))
        return FetchResult(leads=leads, cursor=str(page + 1), has_more=page < total_pages)

    def enrich(self, lead: dict) -> dict:
        if self.demo_mode:
            return {"title": lead.get("title", ""), "seniority": "director",
                    "demo": True, "source": "apollo"}
        body = {"api_key": self._key(), "email": lead.get("email"),
                "name": lead.get("full_name"), "organization_name": lead.get("company_name")}
        with httpx.Client(timeout=45) as client:
            resp = client.post(f"{self._base}/people/match", json=body)
        if resp.status_code >= 400:
            raise ConnectorError(f"Apollo enrich failed: {resp.text[:300]}")
        return resp.json().get("person", {})
