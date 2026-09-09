"""Salesforce connector.

Reads Leads and Contacts through the REST API and writes activity back, so a
qualified LeadSense record and its reply intent land on the record the sales team
actually works from.

Auth: OAuth 2.0 username-password flow by default (simple for demos). For
production, swap ``_authenticate`` for the JWT bearer flow with a connected app
certificate — the rest of the class is unchanged.
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
class SalesforceConnector(SourceConnector):
    key = "salesforce"
    display_name = "Salesforce"
    description = "Sync Leads and Contacts from Salesforce and write activity back."
    kind = ConnectorKind.CRM
    capabilities = {Capability.FETCH, Capability.PUSH, Capability.INCREMENTAL, Capability.SEARCH}
    config_fields = [
        ConfigField("domain", "My Domain", "text", required=True,
                    help="e.g. acme.my.salesforce.com"),
        ConfigField("client_id", "Consumer key", "password", required=True, secret=True),
        ConfigField("client_secret", "Consumer secret", "password", required=True, secret=True),
        ConfigField("username", "Username", "text", required=True),
        ConfigField("password", "Password + security token", "password", required=True, secret=True),
        ConfigField("object", "Object", "select", options=["Lead", "Contact"], default="Lead"),
        ConfigField("soql_filter", "Extra SOQL filter", "text",
                    help="Optional WHERE clause fragment, e.g. Status = 'Open'"),
        ConfigField("api_version", "API version", "text", default="v60.0"),
    ]

    def has_credentials(self) -> bool:
        return bool(
            (self.config.get("domain") or settings.salesforce_domain)
            and (self.config.get("client_id") or settings.salesforce_client_id)
        )

    # -- auth ------------------------------------------------------------
    def _authenticate(self) -> tuple[str, str]:
        domain = self.setting("domain", "salesforce_domain")
        payload = {
            "grant_type": "password",
            "client_id": self.setting("client_id", "salesforce_client_id"),
            "client_secret": self.setting("client_secret", "salesforce_client_secret"),
            "username": self.setting("username", "salesforce_username"),
            "password": self.setting("password", "salesforce_password"),
        }
        url = f"https://{domain}/services/oauth2/token"
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, data=payload)
        if resp.status_code >= 400:
            raise ConnectorError(f"Salesforce auth failed: {resp.text[:300]}")
        data = resp.json()
        return data["access_token"], data["instance_url"]

    def test_connection(self) -> dict:
        if self.demo_mode:
            return {"ok": True, "message": "Demo mode — synthetic Salesforce records",
                    "details": {"demo": True}}
        try:
            token, instance = self._authenticate()
            return {"ok": True, "message": "Authenticated",
                    "details": {"instance_url": instance, "token_prefix": token[:6]}}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "details": {}}

    # -- read ------------------------------------------------------------
    def _soql(self, cursor: str, limit: int) -> str:
        obj = self.config.get("object", "Lead")
        fields = [
            "Id", "FirstName", "LastName", "Email", "Title", "Phone",
            "LastModifiedDate",
        ]
        fields += ["Company", "Industry", "NumberOfEmployees", "City", "Country", "Website"] \
            if obj == "Lead" else ["Account.Name", "Account.Industry", "MailingCity", "MailingCountry"]
        where: list[str] = []
        if cursor:
            where.append(f"LastModifiedDate > {cursor}")
        if self.config.get("soql_filter"):
            where.append(f"({self.config['soql_filter']})")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        return (
            f"SELECT {', '.join(fields)} FROM {obj}{clause} "
            f"ORDER BY LastModifiedDate ASC LIMIT {limit}"
        )

    @staticmethod
    def _to_lead(rec: dict[str, Any], obj: str) -> RawLead:
        account = rec.get("Account") or {}
        name = " ".join(x for x in [rec.get("FirstName"), rec.get("LastName")] if x)
        location = ", ".join(
            x for x in [rec.get("City") or rec.get("MailingCity"),
                        rec.get("Country") or rec.get("MailingCountry")] if x
        )
        return RawLead(
            external_id=rec.get("Id", ""),
            full_name=name.strip(),
            email=(rec.get("Email") or "").lower(),
            title=rec.get("Title") or "",
            company_name=rec.get("Company") or account.get("Name") or "",
            location=location,
            profile_url=rec.get("Website") or "",
            phone=rec.get("Phone") or "",
            industry=rec.get("Industry") or account.get("Industry") or "",
            employee_count=int(rec.get("NumberOfEmployees") or 0),
            source=f"salesforce:{obj}",
            raw=rec,
        )

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        if self.demo_mode:
            from app.connectors.demo_data import demo_leads
            return FetchResult(leads=demo_leads("salesforce", limit),
                               warnings=["demo mode — no Salesforce credentials configured"])
        token, instance = self._authenticate()
        version = self.config.get("api_version") or settings.salesforce_api_version
        obj = self.config.get("object", "Lead")
        url = f"{instance}/services/data/{version}/query"
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, params={"q": self._soql(cursor, limit)},
                              headers={"Authorization": f"Bearer {token}"})
        if resp.status_code >= 400:
            raise ConnectorError(f"Salesforce query failed: {resp.text[:300]}")
        payload = resp.json()
        records = payload.get("records", [])
        leads = [self._to_lead(r, obj) for r in records]
        next_cursor = records[-1].get("LastModifiedDate", cursor) if records else cursor
        return FetchResult(leads=leads, cursor=next_cursor,
                           has_more=not payload.get("done", True))

    # -- write-back ------------------------------------------------------
    def push(self, records) -> dict:
        """Create Tasks against Salesforce records (next-best-action handoff)."""
        if self.demo_mode:
            items = list(records)
            return {"created": len(items), "demo": True,
                    "ids": [f"00T{i:015d}" for i in range(len(items))]}
        token, instance = self._authenticate()
        version = self.config.get("api_version") or settings.salesforce_api_version
        created: list[str] = []
        with httpx.Client(timeout=60) as client:
            for rec in records:
                body = {
                    "Subject": rec.get("subject", "LeadSense follow-up"),
                    "Description": rec.get("description", ""),
                    "Priority": rec.get("priority", "Normal"),
                    "Status": "Not Started",
                    "WhoId": rec.get("external_id") or None,
                }
                resp = client.post(
                    f"{instance}/services/data/{version}/sobjects/Task",
                    json={k: v for k, v in body.items() if v is not None},
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code >= 400:
                    raise ConnectorError(f"Salesforce task create failed: {resp.text[:300]}")
                created.append(resp.json().get("id", ""))
        return {"created": len(created), "ids": created}
