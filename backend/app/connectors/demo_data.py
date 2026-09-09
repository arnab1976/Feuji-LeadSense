"""Synthetic records so every connector works before credentials exist.

This is what makes ``git clone && make seed && make api`` produce a full working
demo. Nothing here is real data.
"""
from __future__ import annotations

import hashlib

from app.connectors.base import RawLead

_PEOPLE = [
    ("Priya Raghavan", "VP Operations", "Vice President - Banking Operations",
     "Northbridge Bank", "Northbridge Bank Ltd", "Mumbai", "Banking", 8400,
     ["Salesforce", "Snowflake"]),
    ("Daniel Okoro", "Head of Claims Technology", "Head of Claims Technology",
     "Vantage Insurance", "Vantage Insurance Group", "London", "Insurance", 3100,
     ["Guidewire", "Azure"]),
    ("Meera Shankar", "Director, Data", "Director of Data & Analytics",
     "Aurum Capital", "Aurum Capital Partners", "Singapore", "Asset management", 1250,
     ["Databricks", "AWS"]),
    ("Tomas Halvorsen", "CTO", "Chief Technology Officer",
     "Nordkyst Forsikring", "Nordkyst Forsikring AS", "Oslo", "Insurance", 620,
     ["On-premise core"]),
    ("Anita Fernandes", "Manager, Risk", "Senior Manager - Risk Analytics",
     "Crestline Bank", "Crestline Bank PJSC", "Dubai", "Banking", 5900,
     ["SAS", "Oracle"]),
    ("Rohit Menon", "Associate", "Associate - Operations Support",
     "Silverline Mutual", "Silverline Mutual Fund", "Pune", "Asset management", 340,
     ["Excel"]),
    ("Claire Beaumont", "Chief Data Officer", "Chief Data Officer",
     "Helvetia Trust", "Helvetia Trust AG", "Zurich", "Banking", 12000,
     ["Azure", "Collibra"]),
    ("Samuel Adeyemi", "Head of Underwriting", "Head of Underwriting Operations",
     "Ridgeway Assurance", "Ridgeway Assurance Plc", "Lagos", "Insurance", 2200,
     ["Legacy policy admin"]),
    ("Ingrid Sorensen", "Head of Manufacturing IT", "Head of Manufacturing IT",
     "Baltica Pharma", "Baltica Pharma A/S", "Copenhagen", "Pharma", 4600,
     ["OSIsoft PI", "SAP"]),
    ("Sofia Petrova", "VP Engineering", "Vice President of Engineering",
     "Halcyon Systems", "Halcyon Systems GmbH", "Berlin", "Software", 1900,
     ["Kubernetes", "GCP"]),
    ("Arjun Nair", "Head of Data Platform", "Head of Data Platform Engineering",
     "Cobalt Data", "Cobalt Data Pvt Ltd", "Bengaluru", "Software", 880,
     ["Databricks", "Airflow"]),
    ("Aisha Khan", "Chief Information Officer", "Chief Information Officer",
     "Quantile Labs", "Quantile Labs Corp", "Toronto", "IT services", 9800,
     ["Azure", "Snowflake"]),
]


def _slug(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == " ").replace(" ", ".")


def demo_leads(source: str, limit: int = 100, offset: int = 0) -> list[RawLead]:
    """Deterministic synthetic leads.

    The uploaded ``title`` deliberately differs from the canonical title for some
    records so the Verification agent has real MATCH / MISMATCH / NEEDS_REVIEW
    cases to produce rather than a table of green ticks.
    """
    leads: list[RawLead] = []
    window = (_PEOPLE + _PEOPLE)[offset:offset + limit]
    for idx, (name, uploaded_title, _canonical, company, legal, city,
              industry, headcount, tech) in enumerate(window):
        digest = hashlib.sha1(f"{source}:{name}".encode()).hexdigest()[:10]
        domain = "".join(ch for ch in company.lower() if ch.isalpha()) + ".com"
        leads.append(RawLead(
            external_id=f"{source}-{digest}",
            full_name=name,
            email=f"{_slug(name)}@{domain}",
            title=uploaded_title,
            company_name=company if source != "salesforce" else legal,
            location=city,
            profile_url=f"https://{domain}/team/{_slug(name)}",
            phone="",
            industry=industry,
            employee_count=headcount,
            tech_stack=tech,
            source=source,
            raw={"demo": True, "row": idx + 1, "legal_name": legal},
        ))
    return leads


def canonical_profile(full_name: str) -> dict:
    """The 'extracted' view of a demo person, used by the Extraction agent."""
    for (name, _uploaded, canonical, company, legal, city, industry,
         headcount, tech) in _PEOPLE:
        if name == full_name:
            return {
                "full_name": name, "title": canonical, "company_name": legal,
                "location": city, "industry": industry,
                "employee_count": headcount, "tech_stack": tech,
            }
    return {}
