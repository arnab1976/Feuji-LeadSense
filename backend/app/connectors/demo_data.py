"""Synthetic records and demo canonical profiles for Verification demos.

``DEMO_DATA_ACTIVE`` gates the old in-memory ``demo_leads()`` people list
(connector demo-mode without credentials). Leave it False when using CSV
fixtures instead.

``CANONICAL_PROFILES_ACTIVE`` applies uploaded→canonical expansions so
Verification can surface MATCH / MISMATCH / NEEDS_REVIEW on fixture data
(e.g. BFSI prospect list: VP Operations vs Vice President — Banking Operations).
"""
from __future__ import annotations

import hashlib
import re

from app.connectors.base import RawLead

# In-memory connector demo people (empty while False).
DEMO_DATA_ACTIVE = False

# Company/title canonical expansions for fixture Verification demos.
CANONICAL_PROFILES_ACTIVE = True

# (name, uploaded_title, canonical_title, company, legal, city, industry, hc, tech)
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
    ("Aisha Rahman", "VP Engineering", "Vice President of Engineering",
     "Nimbus Data", "Nimbus Data Inc", "Bengaluru", "Software", 720,
     ["Kubernetes", "AWS"]),
    ("Marcus Chen", "Director of Platform", "Director, Platform Engineering",
     "Orbitly", "Orbitly Pte Ltd", "Singapore", "Software", 410,
     ["GCP", "Terraform"]),
    ("Priya Nair", "Head of Data", "Head of Data Platform",
     "Stacklane", "Stacklane Technologies Ltd", "Hyderabad", "Software", 980,
     ["Databricks", "Snowflake"]),
    ("Jonah Wells", "CTO", "Chief Technology Officer",
     "BrightOps", "BrightOps Inc", "Austin", "Software", 260,
     ["AWS", "Kubernetes"]),
    ("Elena Petrova", "VP Product", "Vice President of Product",
     "Quantora", "Quantora GmbH", "Berlin", "Software", 540,
     ["React", "Postgres"]),
]

# Fixture CSVs rotate person names; resolve canonical by company (+ optional title).
# Aligns with salesforce_bfsi_prospect_list.csv and related demo fixtures.
_CANONICAL_BY_COMPANY: dict[str, dict] = {
    "northbridge bank": {
        "company_name": "Northbridge Bank Ltd",
        "location": "Mumbai",
        "industry": "Banking",
        "titles": {
            "vp operations": "Vice President - Banking Operations",
            "operations director": "Vice President - Banking Operations",
        },
    },
    "vantage insurance": {
        "company_name": "Vantage Insurance Group",
        "location": "London",
        "industry": "Insurance",
        "titles": {
            "head of claims technology": "Head of Claims Technology",
        },
    },
    "aurum capital": {
        "company_name": "Aurum Capital Partners",
        "location": "Singapore",
        "industry": "Asset management",
        "titles": {
            "director of data": "Director of Data & Analytics",
            "director, data": "Director of Data & Analytics",
            "data strategy head": "Director of Data & Analytics",
        },
    },
    "crestline bank": {
        "company_name": "Crestline Bank PJSC",
        "location": "Dubai",
        "industry": "Banking",
        "titles": {
            "chief risk officer": "Senior Manager - Risk Analytics",
            "manager, risk": "Senior Manager - Risk Analytics",
            "manager risk": "Senior Manager - Risk Analytics",
        },
    },
    "helvetia trust": {
        "company_name": "Helvetia Trust AG",
        "location": "Zurich",
        "industry": "Banking",
        "titles": {
            "chief data officer": "Chief Data Officer",
        },
    },
    "silverline mutual": {
        "company_name": "Silverline Mutual Fund",
        "location": "Pune",
        "industry": "Asset management",
        "titles": {
            "lifecycle marketing lead": "Associate - Operations Support",
            "associate": "Associate - Operations Support",
        },
    },
    "nordkyst forsikring": {
        "company_name": "Nordkyst Forsikring AS",
        "titles": {"cto": "Chief Technology Officer"},
    },
    "ridgeway assurance": {
        "company_name": "Ridgeway Assurance Plc",
        "titles": {
            "head of underwriting": "Head of Underwriting Operations",
        },
    },
    "baltica pharma": {
        "company_name": "Baltica Pharma A/S",
        "titles": {
            "head of manufacturing it": "Head of Manufacturing IT",
        },
    },
    "nimbus data": {
        "company_name": "Nimbus Data Inc",
        "titles": {"vp engineering": "Vice President of Engineering"},
    },
    "orbitly": {
        "company_name": "Orbitly Pte Ltd",
        "titles": {
            "director of platform": "Director, Platform Engineering",
            "director platform": "Director, Platform Engineering",
        },
    },
    "stacklane": {
        "company_name": "Stacklane Technologies Ltd",
        "titles": {
            "head of data": "Head of Data Platform",
        },
    },
    "brightops": {
        "company_name": "BrightOps Inc",
        "titles": {"cto": "Chief Technology Officer"},
    },
    "quantora": {
        "company_name": "Quantora GmbH",
        "titles": {"vp product": "Vice President of Product"},
    },
}


def _slug(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch == " ").replace(" ", ".")


def _norm_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def demo_leads(source: str, limit: int = 100, offset: int = 0) -> list[RawLead]:
    """Deterministic synthetic leads. Empty while ``DEMO_DATA_ACTIVE`` is False."""
    if not DEMO_DATA_ACTIVE:
        return []

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


def canonical_profile(
    full_name: str = "",
    *,
    title: str = "",
    company_name: str = "",
) -> dict:
    """Return a demo 'extracted' profile when a known company/title (or person) matches.

    Fixture CSVs rotate names (Aarav Mehta, …); lookup is primarily by company.
    """
    if not CANONICAL_PROFILES_ACTIVE:
        return {}

    company_key = _norm_key(company_name)
    entry = _CANONICAL_BY_COMPANY.get(company_key)
    if entry:
        title_key = _norm_key(title)
        titles: dict = entry.get("titles") or {}
        canonical_title = titles.get(title_key) or title
        return {
            "full_name": full_name,
            "title": canonical_title,
            "company_name": entry.get("company_name") or company_name,
            "location": entry.get("location") or "",
            "industry": entry.get("industry") or "",
            "employee_count": entry.get("employee_count", 0),
            "tech_stack": entry.get("tech_stack") or [],
        }

    if not DEMO_DATA_ACTIVE:
        return {}

    for (name, _uploaded, canonical, company, legal, city, industry,
         headcount, tech) in _PEOPLE:
        if name == full_name:
            return {
                "full_name": name, "title": canonical, "company_name": legal,
                "location": city, "industry": industry,
                "employee_count": headcount, "tech_stack": tech,
            }
    return {}


def demo_people_names() -> list[str]:
    if not DEMO_DATA_ACTIVE:
        return []
    return [row[0] for row in _PEOPLE]
