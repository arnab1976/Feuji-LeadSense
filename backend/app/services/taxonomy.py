"""Title, seniority, function and persona normalisation.

Deterministic rules first — they are explainable and free. The Enrichment agent
falls back to the LLM only for titles these patterns do not resolve.
"""
from __future__ import annotations

import re

SENIORITY_RULES: list[tuple[str, str, int]] = [
    # "president" needs the lookbehind or every VP is misread as C-level.
    (r"\b(chief|c[teiofd]o|founder|owner|managing partner)\b|(?<!vice )\bpresident\b",
     "C-level", 100),
    (r"\b(svp|senior vice president)\b", "SVP", 92),
    (r"\b(vp|vice president)\b", "VP", 86),
    (r"\bhead of\b", "Head", 79),
    (r"\b(director)\b", "Director", 73),
    (r"\b(senior manager|principal)\b", "Senior manager", 61),
    (r"\b(manager|lead)\b", "Manager", 52),
    (r"\b(engineer|analyst|associate|specialist|consultant|executive)\b",
     "Individual contributor", 26),
]

FUNCTION_RULES: list[tuple[str, str]] = [
    # Leading word boundary only: these are prefixes, so "operation" must also
    # match "operations" and "technolog" must match "technology".
    (r"\b(data|analytic|bi\b|insight)", "Data"),
    (r"\b(quality|regulatory|validation|compliance)", "Quality"),
    (r"\b(operation|supply|claims|underwriting|servicing|process)", "Operations"),
    (r"\b(technolog|engineering|platform|automation|digital|architect|"
     r"information)", "Technology"),
    (r"\b(product)", "Product"),
    (r"\b(risk|fraud|credit)", "Risk"),
    (r"\b(marketing|growth|demand)", "Marketing"),
    (r"\b(sales|revenue|commercial|account)", "Sales"),
    (r"\b(finance|financial|treasury|accounting)", "Finance"),
]

PERSONA_BY_FUNCTION = {
    "Data": "Data leader",
    "Quality": "Quality leader",
    "Operations": "Operations leader",
    "Technology": "Technology leader",
    "Product": "Product leader",
    "Risk": "Risk leader",
    "Marketing": "Marketing leader",
    "Sales": "Revenue leader",
    "Finance": "Finance leader",
}

SKILL_TAXONOMY = {
    "Data": ["data governance", "analytics", "data quality", "reporting"],
    "Quality": ["gxp", "validation", "audit readiness", "capa"],
    "Operations": ["process design", "service levels", "workforce planning"],
    "Technology": ["cloud migration", "integration", "platform engineering"],
    "Product": ["roadmapping", "discovery", "pricing"],
    "Risk": ["model risk", "controls", "regulatory reporting"],
    "Marketing": ["demand generation", "segmentation", "campaign ops"],
    "Sales": ["pipeline management", "forecasting", "territory planning"],
    "Finance": ["planning", "cost control", "reporting"],
}

# Common abbreviation expansions. Punctuation is stripped before these run, so
# the patterns stay simple: "Sr. Mgr, Risk" is already "sr mgr risk" by here.
EXPANSIONS = {
    r"\bvp\b": "vice president",
    r"\bsvp\b": "senior vice president",
    r"\bevp\b": "executive vice president",
    r"\bavp\b": "assistant vice president",
    r"\bcto\b": "chief technology officer",
    r"\bcio\b": "chief information officer",
    r"\bcoo\b": "chief operating officer",
    r"\bcdo\b": "chief data officer",
    r"\bceo\b": "chief executive officer",
    r"\bcfo\b": "chief financial officer",
    r"\bsr\b": "senior",
    r"\bjr\b": "junior",
    r"\bmgr\b": "manager",
    r"\bdir\b": "director",
    r"\bops\b": "operations",
    r"\beng\b": "engineering",
    r"\bit\b": "information technology",
}


def normalize_title(title: str) -> str:
    """Lower-case, de-punctuate, expand abbreviations, then title-case.

    Punctuation is removed first so that "Sr. Mgr, Risk" and "Sr Mgr Risk" take
    the same path — otherwise the abbreviation patterns silently miss whichever
    variant the source system happened to use.
    """
    text = (title or "").strip().lower()
    text = re.sub(r"[.,;:/|()\[\]]+", " ", text)
    text = re.sub(r"[\s\-–—_&]+", " ", text).strip()
    for pattern, replacement in EXPANSIONS.items():
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+", " ", text).strip()
    return " ".join(word.capitalize() if word not in {"of", "and", "the"} else word
                    for word in text.split())


def seniority(title: str) -> tuple[str, int]:
    text = normalize_title(title).lower()
    for pattern, label, rank in SENIORITY_RULES:
        if re.search(pattern, text):
            return label, rank
    return "Unclassified", 40


def function_of(title: str) -> str:
    text = normalize_title(title).lower()
    for pattern, label in FUNCTION_RULES:
        if re.search(pattern, text):
            return label
    return "Business"


def persona_of(title: str) -> str:
    return PERSONA_BY_FUNCTION.get(function_of(title), "General business")


def skills_for(title: str) -> list[str]:
    return SKILL_TAXONOMY.get(function_of(title), ["stakeholder management"])
