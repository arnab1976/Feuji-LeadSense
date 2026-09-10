"""Unit tests for the deterministic agent logic."""
from app.services.scoring import DEFAULT_WEIGHTS, band_for, score_lead
from app.services.taxonomy import normalize_title, persona_of, seniority


def test_title_normalisation_expands_abbreviations():
    assert normalize_title("VP Ops") == "Vice President Operations"
    assert normalize_title("Sr. Mgr, Risk") == "Senior Manager Risk"


def test_seniority_ranks_c_level_above_manager():
    assert seniority("Chief Data Officer")[1] > seniority("Manager, Risk")[1]
    assert seniority("Vice President of Engineering")[0] == "VP"


def test_persona_derives_from_function():
    assert persona_of("Director of Data & Analytics") == "Data leader"
    assert persona_of("Head of Underwriting Operations") == "Operations leader"


def test_scoring_is_explainable_and_weight_sensitive():
    kwargs = dict(title="Chief Data Officer", industry="Banking",
                  employee_count=12000, tech_stack=["Azure", "Collibra"],
                  engagement={"opened": 2})
    base = score_lead(**kwargs, weights=DEFAULT_WEIGHTS)
    assert 0 <= base["score"] <= 100
    assert set(base["factors"]) == set(DEFAULT_WEIGHTS)
    for factor in base["factors"].values():
        assert factor["evidence"]

    seniority_heavy = score_lead(**kwargs, weights={**DEFAULT_WEIGHTS,
                                                    "seniority": 50})
    assert seniority_heavy["score"] != base["score"]


def test_score_bands():
    assert band_for(90) == "HOT"
    assert band_for(75) == "HIGH"
    assert band_for(60) == "MEDIUM"
    assert band_for(30) == "LOW"


def test_verification_treats_expanded_titles_as_a_match():
    from app.agents.verification import VerificationAgent

    status, confidence, reason, method = VerificationAgent()._compare(
        "title", "VP Operations", "Vice President Operations", 0.86, 0.62)
    assert status == "MATCH"
    assert confidence > 0.9


def test_verification_flags_a_material_company_difference():
    from app.agents.verification import VerificationAgent

    status, *_ = VerificationAgent()._compare(
        "company_name", "Aurum Capital", "Zenith Holdings", 0.90, 0.70)
    assert status in ("MISMATCH", "NEEDS_REVIEW")


def test_verification_ignores_legal_suffixes():
    from app.agents.verification import VerificationAgent

    status, *_ = VerificationAgent()._compare(
        "company_name", "Northbridge Bank", "Northbridge Bank Ltd", 0.90, 0.70)
    assert status == "MATCH"


def test_extraction_applies_company_canonical_profile():
    """BFSI fixture companies get canonical expansions for Verification mismatches."""
    from types import SimpleNamespace

    from app.agents.extraction import ExtractionAgent

    lead = SimpleNamespace(
        full_name="Aarav Mehta",
        title="VP Operations",
        company_name="Northbridge Bank",
        location="Mumbai",
        email="aarav.mehta1@northbridgebank.com",
        phone="",
        connector_key="salesforce",
        raw_payload={"demo": True, "industry": "BFSI"},
    )
    payload = ExtractionAgent._extract(lead)
    assert payload["canonical_applied"] is True
    assert payload["title"] == "Vice President - Banking Operations"
    assert payload["company_name"] == "Northbridge Bank Ltd"


def test_extraction_unknown_company_stays_same_source():
    from types import SimpleNamespace

    from app.agents.extraction import ExtractionAgent

    lead = SimpleNamespace(
        full_name="Someone Else",
        title="Analyst",
        company_name="Acme Widgets LLC",
        location="NYC",
        email="someone@acme.example",
        phone="",
        connector_key="salesforce",
        raw_payload={},
    )
    payload = ExtractionAgent._extract(lead)
    assert payload["canonical_applied"] is False
    assert payload["title"] == "Analyst"
    assert payload["company_name"] == "Acme Widgets LLC"


def test_agent_catalog_has_thirteen_entries():
    from app.agents import catalog

    entries = catalog()
    assert len(entries) == 13
    for entry in entries:
        assert entry["role"] and entry["execution_strategy"] and entry["stack"]
    orchestrator = next(e for e in entries if e["key"] == "supervisor")
    assert orchestrator["kind"] == "orchestrator"
    assert orchestrator["number"] == 0
    assert orchestrator["name"] == "Workflow Orchestrator"
    ingestion = next(e for e in entries if e["key"] == "ingestion")
    assert ingestion["number"] == 1
    assert ingestion["kind"] == "agent"
