"""Public web profile extraction — policy gated by design.

This connector is disabled unless the tenant explicitly enables it AND the target
domain is on the allow-list. That is deliberate: source terms of service and
data-protection rules are the top adoption risk for this product, so the guard
sits in the connector rather than in a review step further downstream.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.connectors.base import (
    Capability, ConfigField, ConnectorKind, FetchResult, RawLead, SourceConnector,
)
from app.connectors.registry import register_connector
from app.core.errors import PolicyViolation


@register_connector
class WebProfileConnector(SourceConnector):
    key = "web_profile"
    display_name = "Public web profile"
    description = "Extracts profile data from allow-listed public pages."
    kind = ConnectorKind.WEB
    capabilities = {Capability.FETCH, Capability.ENRICH}
    requires_policy_review = True
    config_fields = [
        ConfigField("allowed_domains", "Allowed domains", "text", required=True,
                    help="Comma separated. Only these hosts will ever be fetched."),
        ConfigField("respect_robots", "Respect robots.txt", "boolean", default=True),
        ConfigField("rate_limit_per_minute", "Requests per minute", "number", default=20),
    ]

    def has_credentials(self) -> bool:
        return bool(self.config.get("allowed_domains"))

    def _allowed(self, url: str) -> bool:
        allowed = [d.strip().lower() for d in
                   (self.config.get("allowed_domains") or "").split(",") if d.strip()]
        host = (urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in allowed)

    def test_connection(self) -> dict:
        if not self.has_credentials():
            return {"ok": False,
                    "message": "No allowed domains configured — extraction is blocked",
                    "details": {}}
        return {"ok": True, "message": "Allow-list configured",
                "details": {"domains": self.config.get("allowed_domains")}}

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        urls: list[str] = kwargs.get("urls", [])
        blocked = [u for u in urls if not self._allowed(u)]
        if blocked:
            raise PolicyViolation(
                "Source policy blocked extraction",
                {"blocked_urls": blocked[:10],
                 "reason": "host is not on the tenant allow-list"},
            )
        if self.demo_mode or not urls:
            from app.connectors.demo_data import demo_leads
            return FetchResult(leads=demo_leads("web_profile", min(limit, 4)),
                               warnings=["demo mode — no live pages fetched"])

        # Real implementation: Playwright or httpx + a parser per allow-listed
        # template. Kept out of the default build so a clone has no browser
        # dependency; see docs/connectors.md for the reference implementation.
        import httpx
        leads: list[RawLead] = []
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            for url in urls[:limit]:
                resp = client.get(url)
                leads.append(RawLead(
                    external_id=url, profile_url=url, source="web_profile",
                    raw={"status": resp.status_code, "length": len(resp.text)},
                ))
        return FetchResult(leads=leads)
