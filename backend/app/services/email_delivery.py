"""Outbound email. Console provider for demos, AWS SES for real sending."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("leadsense.email")


@dataclass
class SendResult:
    ok: bool
    provider: str
    message_id: str = ""
    error: str = ""


class ConsoleProvider:
    name = "console"

    def send(self, to: str, subject: str, body: str, **kwargs) -> SendResult:
        log.info("[console-send] to=%s subject=%s", to, subject)
        # Simulate the one deterministic bounce that makes the analytics screen
        # honest about delivery failures.
        if to.endswith("@invalid.test"):
            return SendResult(ok=False, provider=self.name, error="hard bounce")
        return SendResult(ok=True, provider=self.name,
                          message_id=f"0100{uuid.uuid4().hex[:12]}")


class SESProvider:
    name = "ses"

    def send(self, to: str, subject: str, body: str, **kwargs) -> SendResult:
        import boto3
        client = boto3.client(
            "ses", region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        params = {
            "Source": settings.ses_from_address,
            "Destination": {"ToAddresses": [to]},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        }
        if settings.ses_configuration_set:
            params["ConfigurationSetName"] = settings.ses_configuration_set
        try:
            resp = client.send_email(**params)
            return SendResult(ok=True, provider=self.name,
                              message_id=resp["MessageId"])
        except Exception as exc:
            return SendResult(ok=False, provider=self.name, error=str(exc))


def get_provider():
    return SESProvider() if settings.email_provider == "ses" else ConsoleProvider()
