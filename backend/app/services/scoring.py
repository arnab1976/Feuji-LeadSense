"""ICP and lead scoring.

Transparent weighted rules. Every factor returns a 0-100 sub-score plus the
evidence behind it, so the portal can show a sales team exactly why a lead ranked
where it did. Learned propensity models slot in behind the same interface once
enough labelled conversion data exists — see ``score_lead``'s docstring.
"""
from __future__ import annotations

import re

from app.services.taxonomy import persona_of, seniority

DEFAULT_WEIGHTS = {
    "icp_fit": 30, "seniority": 20, "industry_fit": 15, "company_size": 10,
    "technology_fit": 10, "engagement": 10, "historical_conversion": 5,
}

TARGET_INDUSTRIES = {"banking", "insurance", "pharma", "software", "financial services"}
ADJACENT_INDUSTRIES = {"asset management", "medical devices", "it services",
                       "healthcare", "manufacturing"}
MODERN_TECH = re.compile(
    r"snowflake|databricks|azure|aws|gcp|kubernetes|veeva|guidewire|siemens|"
    r"terraform|bigquery|airflow|collibra|osisoft|salesforce|hubspot",
    re.IGNORECASE,
)
LEGACY_TECH = re.compile(r"legacy|on-?premise|paper|excel|mainframe|access db",
                         re.IGNORECASE)

BANDS = [(85, "HOT"), (70, "HIGH"), (50, "MEDIUM"), (0, "LOW")]


def band_for(score: int) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "LOW"


def _icp_fit(title: str, persona: str, rank: int) -> tuple[int, str]:
    base = 88 if persona not in {"General business", "Product leader"} else 62
    value = int(base * 0.5 + rank * 0.5)
    return value, f"{persona} with a {seniority(title)[0].lower()} title"


def _industry_fit(industry: str) -> tuple[int, str]:
    text = (industry or "").strip().lower()
    if text in TARGET_INDUSTRIES:
        return 90, f"{industry} is a core target industry"
    if text in ADJACENT_INDUSTRIES:
        return 72, f"{industry} is an adjacent industry"
    return 50, f"{industry or 'Unknown industry'} is outside the target list"


def _company_size(count: int) -> tuple[int, str]:
    if count > 5000:
        return 95, f"{count:,} employees - enterprise band"
    if count > 2000:
        return 80, f"{count:,} employees - upper mid-market"
    if count > 800:
        return 64, f"{count:,} employees - mid-market"
    if count > 0:
        return 38, f"{count:,} employees - below the target band"
    return 45, "Employee count unknown"


def _technology_fit(stack) -> tuple[int, str]:
    text = " ".join(stack) if isinstance(stack, list) else str(stack or "")
    if MODERN_TECH.search(text):
        return 90, f"Modern data stack detected ({text[:60]})"
    if LEGACY_TECH.search(text):
        return 36, f"Legacy or manual tooling ({text[:60]})"
    return 64, "Technology signals inconclusive"


def _engagement(signals: dict) -> tuple[int, str]:
    if signals.get("replied"):
        return 95, "Replied to a previous sequence"
    if signals.get("clicked"):
        return 82, "Clicked a previous email"
    if signals.get("opened"):
        return 70, f"Opened {signals.get('opened')} previous email(s)"
    return 18, "No prior engagement recorded"


def _historical(signals: dict) -> tuple[int, str]:
    rate = float(signals.get("segment_conversion_rate") or 0)
    if rate >= 0.12:
        return 95, f"Segment converts at {rate:.0%}"
    if rate >= 0.08:
        return 80, f"Segment converts at {rate:.0%}"
    if rate > 0:
        return 55, f"Segment converts at {rate:.0%}"
    return 60, "No conversion history for this segment yet"


def score_lead(
    *, title: str, industry: str = "", employee_count: int = 0,
    tech_stack=None, engagement: dict | None = None, weights: dict | None = None,
) -> dict:
    """Return score, band and per-factor evidence.

    To introduce a learned model, compute ``propensity`` here from your ranking
    model and blend it as an extra weighted factor. Keep the rule factors so the
    explanation stays intact — a score sales cannot argue with is a score sales
    will not use.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    engagement = engagement or {}
    sen_label, sen_rank = seniority(title)
    persona = persona_of(title)

    factors: dict[str, dict] = {}
    icp_v, icp_e = _icp_fit(title, persona, sen_rank)
    factors["icp_fit"] = {"value": icp_v, "evidence": icp_e}
    factors["seniority"] = {"value": sen_rank, "evidence": sen_label}
    ind_v, ind_e = _industry_fit(industry)
    factors["industry_fit"] = {"value": ind_v, "evidence": ind_e}
    size_v, size_e = _company_size(employee_count)
    factors["company_size"] = {"value": size_v, "evidence": size_e}
    tech_v, tech_e = _technology_fit(tech_stack)
    factors["technology_fit"] = {"value": tech_v, "evidence": tech_e}
    eng_v, eng_e = _engagement(engagement)
    factors["engagement"] = {"value": eng_v, "evidence": eng_e}
    hist_v, hist_e = _historical(engagement)
    factors["historical_conversion"] = {"value": hist_v, "evidence": hist_e}

    total_weight = sum(weights.values()) or 1
    score = round(
        sum(factors[k]["value"] * weights.get(k, 0) for k in factors) / total_weight
    )
    for key in factors:
        factors[key]["weight"] = weights.get(key, 0)
        factors[key]["contribution"] = round(
            factors[key]["value"] * weights.get(key, 0) / total_weight, 2
        )

    return {
        "score": int(score), "band": band_for(int(score)),
        "persona": persona, "seniority": sen_label,
        "factors": factors, "weights": weights,
    }
