"""CSV over HTTP(S) or S3 — scheduled exports dropped on a URL or bucket."""
from __future__ import annotations

import httpx

from app.connectors.base import (
    Capability, ConfigField, ConnectorKind, FetchResult, SourceConnector,
)
from app.connectors.manual_upload import ManualUploadConnector
from app.connectors.registry import register_connector
from app.core.errors import ConnectorError


@register_connector
class CsvUrlConnector(SourceConnector):
    key = "csv_url"
    display_name = "CSV feed (URL or S3)"
    description = "Scheduled CSV exports pulled from an HTTPS URL or S3 object."
    kind = ConnectorKind.FILE
    capabilities = {Capability.FETCH, Capability.INCREMENTAL}
    config_fields = [
        ConfigField("url", "File URL", "text", required=True,
                    help="https:// URL or s3://bucket/key"),
        ConfigField("auth_header", "Authorization header", "password", secret=True,
                    help="Optional. Sent verbatim as the Authorization header."),
    ]

    def has_credentials(self) -> bool:
        return bool(self.config.get("url"))

    def test_connection(self) -> dict:
        url = self.config.get("url", "")
        if not url:
            return {"ok": False, "message": "No URL configured", "details": {}}
        if url.startswith("s3://"):
            return {"ok": True, "message": "S3 URI accepted (validated at fetch time)",
                    "details": {"uri": url}}
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.head(url, headers=self._headers())
            return {"ok": resp.status_code < 400,
                    "message": f"HTTP {resp.status_code}",
                    "details": {"content_type": resp.headers.get("content-type", "")}}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "details": {}}

    def _headers(self) -> dict:
        header = self.config.get("auth_header")
        return {"Authorization": header} if header else {}

    def _read_bytes(self) -> tuple[bytes, str]:
        url = self.config.get("url", "")
        if url.startswith("s3://"):
            import boto3
            bucket, _, key = url[5:].partition("/")
            body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
            return body, key
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url, headers=self._headers())
        if resp.status_code >= 400:
            raise ConnectorError(f"Feed returned HTTP {resp.status_code}")
        return resp.content, url.rsplit("/", 1)[-1] or "feed.csv"

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        if self.demo_mode:
            from app.connectors.demo_data import demo_leads
            return FetchResult(leads=demo_leads("csv_url", limit),
                               warnings=["demo mode — no URL configured"])
        content, filename = self._read_bytes()
        leads, report = ManualUploadConnector(self.config).parse(content, filename)
        return FetchResult(leads=leads[:limit],
                           warnings=[e["reason"] for e in report["errors"][:5]])
