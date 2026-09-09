"""Manual upload — CSV and Excel files a user drops into the portal.

Column detection is fuzzy: headers like "Job Title", "job_title" and "Position"
all map to ``title``. The detected mapping is returned to the UI so a user can
override it before the ingestion job is created.
"""
from __future__ import annotations

import io
from typing import Any

from app.connectors.base import (
    Capability, ConfigField, ConnectorKind, FetchResult, RawLead, SourceConnector,
)
from app.connectors.registry import register_connector
from app.core.errors import ValidationFailure

# Canonical field -> accepted header aliases (lower-cased, non-alphanumeric stripped)
HEADER_ALIASES: dict[str, list[str]] = {
    "full_name": ["fullname", "name", "contactname", "leadname", "personname"],
    "first_name": ["firstname", "givenname", "fname"],
    "last_name": ["lastname", "surname", "familyname", "lname"],
    "email": ["email", "emailaddress", "workemail", "businessemail", "mail"],
    "title": ["title", "jobtitle", "position", "role", "designation"],
    "company_name": ["company", "companyname", "organization", "organisation", "account", "employer"],
    "location": ["location", "city", "country", "region", "geo"],
    "profile_url": ["profileurl", "url", "link", "profile", "website", "linkedin"],
    "phone": ["phone", "phonenumber", "mobile", "telephone", "contactnumber"],
    "industry": ["industry", "sector", "vertical"],
    "employee_count": ["employeecount", "employees", "companysize", "headcount", "size"],
    "tech_stack": ["techstack", "technology", "technologies", "tools", "stack"],
}


def _norm(header: str) -> str:
    return "".join(ch for ch in str(header).lower() if ch.isalnum())


def detect_mapping(headers: list[str]) -> dict[str, str]:
    """Map source headers onto canonical LeadSense fields."""
    mapping: dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for header in headers:
            if _norm(header) in aliases:
                mapping[canonical] = header
                break
    return mapping


@register_connector
class ManualUploadConnector(SourceConnector):
    key = "manual_upload"
    display_name = "Manual upload"
    description = "CSV or Excel files uploaded directly by a user."
    kind = ConnectorKind.FILE
    capabilities = {Capability.FETCH}
    config_fields = [
        ConfigField(
            name="delimiter", label="CSV delimiter", type="select",
            options=[",", ";", "|", "\t"], default=",",
            help="Only applies to .csv files.",
        ),
        ConfigField(
            name="skip_rows", label="Header rows to skip", type="number", default=0,
            help="Use when the export has a title block above the header row.",
        ),
    ]

    def has_credentials(self) -> bool:  # files need no credentials
        return True

    def test_connection(self) -> dict:
        return {"ok": True, "message": "Manual upload is always available", "details": {}}

    # -- parsing ---------------------------------------------------------
    def parse(
        self,
        content: bytes,
        filename: str,
        mapping: dict[str, str] | None = None,
    ) -> tuple[list[RawLead], dict[str, Any]]:
        """Parse an uploaded file into RawLead objects.

        Returns ``(leads, report)`` where report carries the detected mapping,
        the headers found and any per-row errors.
        """
        import pandas as pd

        skip = int(self.config.get("skip_rows") or 0)
        name = filename.lower()
        try:
            if name.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(content), skiprows=skip, dtype=str)
            elif name.endswith((".csv", ".tsv", ".txt")):
                delim = "\t" if name.endswith(".tsv") else (self.config.get("delimiter") or ",")
                df = pd.read_csv(io.BytesIO(content), skiprows=skip, dtype=str, sep=delim)
            else:
                raise ValidationFailure(f"Unsupported file type: {filename}")
        except ValidationFailure:
            raise
        except Exception as exc:
            raise ValidationFailure(f"Could not read {filename}: {exc}") from exc

        df = df.fillna("")
        headers = [str(c) for c in df.columns]
        resolved = mapping or detect_mapping(headers)

        leads: list[RawLead] = []
        errors: list[dict] = []
        for idx, row in df.iterrows():
            def val(fieldname: str) -> str:
                col = resolved.get(fieldname)
                return str(row.get(col, "")).strip() if col else ""

            full_name = val("full_name")
            if not full_name:
                full_name = " ".join(x for x in [val("first_name"), val("last_name")] if x).strip()

            try:
                headcount = int(float(val("employee_count") or 0))
            except ValueError:
                headcount = 0
            tech_stack = [
                item.strip() for item in val("tech_stack").replace("|", ";").split(";")
                if item.strip()
            ]

            lead = RawLead(
                external_id=f"row-{int(idx) + 1 + skip}",
                full_name=full_name,
                email=val("email").lower(),
                title=val("title"),
                company_name=val("company_name"),
                location=val("location"),
                profile_url=val("profile_url"),
                phone=val("phone"),
                industry=val("industry"),
                employee_count=headcount,
                tech_stack=tech_stack,
                source=self.key,
                raw={str(k): str(v) for k, v in row.to_dict().items()},
            )
            ok, reason = lead.is_valid()
            if not ok:
                errors.append({"row": int(idx) + 1, "reason": reason})
                continue
            leads.append(lead)

        report = {
            "headers": headers,
            "mapping": resolved,
            "unmapped_headers": [h for h in headers if h not in resolved.values()],
            "rows_read": int(len(df)),
            "rows_invalid": len(errors),
            "errors": errors[:50],
        }
        return leads, report

    def fetch(self, cursor: str = "", limit: int = 100, **kwargs) -> FetchResult:
        content: bytes | None = kwargs.get("content")
        filename: str = kwargs.get("filename", "upload.csv")
        if content is None:
            raise ValidationFailure("Manual upload requires file content")
        leads, report = self.parse(content, filename, kwargs.get("mapping"))
        return FetchResult(leads=leads[:limit], warnings=[e["reason"] for e in report["errors"][:5]])
