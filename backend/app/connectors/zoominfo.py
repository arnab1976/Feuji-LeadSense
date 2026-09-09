"""ZoomInfo connector (skeleton).

Included as the worked example of adding a fourth vendor: the auth exchange and
the response mapping are the only parts that differ from Apollo. Fill in
``_authenticate`` and ``_to_lead`` against your contract's API surface.
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

BASE = "https://api.zoominfo.com"


@register_connector
class ZoomInfoConnector(SourceConnector):
    key = "zoominfo"
    display_name = "ZoomInfo"
    description = "Contact and company intelligence from ZoomInfo."
    kind = ConnectorKind.ENRICHMENT
    capabilities = {Capability.FETCH, Capability.SEARCH, Capability.ENRICH}
    requires_policy_review = True
    config_fields = [
        ConfigField("username", "Username", "text", required=True),
        ConfigField("password", "Password", "password", required=True, secret=True),
        ConfigField("job_titles", "Target titles", "text"),
        ConfigField("industries", "Industries", "text"),
    ]

    def has_credentials(self) -> bool:
        return bool(self.config.get("username") or settings.zoominfo_username)

    def _authenticate(self) -> str:
        payload = {"username": self.setting("username", "zoominfo_username"),
                   "password": self.setting("password", "zoominfo_password")}
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{BASE}/authenticate", json=payload)
        if resp.status_code >= 400:
            raise ConnectorError(f"ZoomInfo auth failed: {resp.text[:200]}")
        return resp.json().get("jwt", "")

    def test_connection(self) -> dict:
        if self.demo_mode:
            return {"ok": True, "message": "Demo mode — synthetic ZoomInfo results",
                    "details": {"demo": True}}
        try:
            token = self._authenticate()
            return {"ok": bool(token), "message": "Authenticated", "details": {}}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "details": {}}

    @staticmethod
    def _to_lead(rec: dict[str, Any]) -> RawLead:
        return RawLead(
            external_id=str(rec.get("id", "")),
            full_name=rec.get("fullName", ""),
            email=(rec.get("email") or "").lower(),
            title=rec.get("jobTitle", ""),
            company_name=(rec.get("company") or {}).get("name", ""),
            location=rec.get("city", ""),
            industry=(rec.get("company") or {}).get("industry", ""),
            employee_count=int((rec.get("company") or {}).get("employeeCount") or 0),
            source="zoominfo:contact",
            raw=rec,
        )

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        if self.demo_mode:
            from app.connectors.demo_data import demo_leads
            return FetchResult(leads=demo_leads("zoominfo", limit),
                               warnings=["demo mode — no ZoomInfo credentials configured"])
        token = self._authenticate()
        body = {"page": int(cursor or 1), "rpp": min(limit, 100),
                "jobTitle": self.config.get("job_titles", ""),
                "industryKeywords": self.config.get("industries", "")}
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{BASE}/search/contact", json=body,
                               headers={"Authorization": f"Bearer {token}"})
        if resp.status_code >= 400:
            raise ConnectorError(f"ZoomInfo search failed: {resp.text[:300]}")
        payload = resp.json()
        leads = [self._to_lead(r) for r in payload.get("data", [])]
        page = int(cursor or 1)
        return FetchResult(leads=leads, cursor=str(page + 1),
                           has_more=len(leads) >= min(limit, 100))
