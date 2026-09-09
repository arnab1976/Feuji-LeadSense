"""The connector layer is the extension point, so it gets the most tests."""
import io

from app.connectors import build_connector, list_connectors, registry_keys
from app.connectors.manual_upload import ManualUploadConnector, detect_mapping


def test_every_connector_is_registered():
    keys = registry_keys()
    for expected in ["manual_upload", "salesforce", "hubspot", "apollo",
                     "csv_url", "zoominfo", "web_profile"]:
        assert expected in keys


def test_catalog_exposes_a_config_form():
    for descriptor in list_connectors():
        assert descriptor["key"]
        assert descriptor["display_name"]
        assert isinstance(descriptor["config_fields"], list)
        assert descriptor["capabilities"]


def test_header_detection_handles_aliases():
    mapping = detect_mapping(["Full Name", "Job Title", "Company Name",
                              "Work Email", "City"])
    assert mapping["full_name"] == "Full Name"
    assert mapping["title"] == "Job Title"
    assert mapping["company_name"] == "Company Name"
    assert mapping["email"] == "Work Email"


def test_manual_upload_parses_csv_and_rejects_bad_rows():
    csv = (
        "Full Name,Job Title,Company,Work Email\n"
        "Jane Doe,VP Operations,Acme Ltd,jane.doe@acme.com\n"
        ",,,\n"
        "Bad Email,Director,Beta Inc,not-an-email\n"
    )
    connector = ManualUploadConnector()
    leads, report = connector.parse(csv.encode(), "leads.csv")
    assert report["rows_read"] == 3
    assert len(leads) == 1
    assert leads[0].full_name == "Jane Doe"
    assert report["rows_invalid"] == 2


def test_manual_upload_splits_first_and_last_name():
    csv = "First Name,Last Name,Email\nAda,Lovelace,ada@analytical.io\n"
    leads, _ = ManualUploadConnector().parse(csv.encode(), "l.csv")
    assert leads[0].full_name == "Ada Lovelace"


def test_crm_connectors_fall_back_to_demo_mode_without_credentials():
    for key in ("salesforce", "hubspot", "apollo", "zoominfo"):
        connector = build_connector(key, {})
        assert connector.demo_mode is True
        result = connector.fetch(limit=5)
        assert len(result.leads) == 5
        assert all(lead.full_name for lead in result.leads)
        assert connector.test_connection()["ok"] is True


def test_web_profile_blocks_hosts_outside_the_allow_list():
    from app.core.errors import PolicyViolation

    connector = build_connector("web_profile", {"allowed_domains": "example.com"})
    try:
        connector.fetch(urls=["https://not-allowed.test/person"])
    except PolicyViolation as exc:
        assert "blocked_urls" in exc.detail
    else:
        raise AssertionError("expected the allow-list to block this host")


def test_dedupe_key_prefers_email():
    from app.connectors.base import RawLead

    a = RawLead(full_name="A B", email="X@Example.com", company_name="Acme")
    b = RawLead(full_name="Different Name", email="x@example.com", company_name="Other")
    assert a.dedupe_key() == b.dedupe_key()
