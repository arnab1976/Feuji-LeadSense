"""End-to-end walk of the product story through the HTTP API.

Upload -> verify -> enrich -> score -> segment -> campaign -> generate ->
compliance -> approve -> send -> analytics -> reply -> next best action.
"""
import io
import json


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_auth_and_permissions(client, auth):
    me = client.get("/api/v1/auth/me", headers=auth).json()
    assert me["tenant_name"] == "Feuji Revenue Operations"
    assert "email:approve" in me["permissions"]


def test_connector_catalog_is_served(client, auth):
    catalog = client.get("/api/v1/sources/catalog", headers=auth).json()
    keys = {c["key"] for c in catalog}
    assert {"manual_upload", "salesforce", "hubspot", "apollo"} <= keys


def test_connect_and_import_needs_credentials_without_keys(client, auth):
    """Workflow Agent 01 path: refuse silent live import when credentials are empty."""
    resp = client.post(
        "/api/v1/sources/connectors/hubspot/connect-and-import",
        json={
            "name": "HubSpot workflow",
            "config": {},
            "limit": 5,
            "run_pipeline": False,
            "allow_demo": False,
            "test_only": False,
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "needs_credentials"
    assert body["sync"] is None
    assert body["config_fields"]


def test_connect_and_import_demo_when_allowed(client, auth):
    resp = client.post(
        "/api/v1/sources/connectors/csv_url/connect-and-import",
        json={
            "name": "CSV feed workflow",
            "config": {},
            "limit": 5,
            "run_pipeline": True,
            "allow_demo": True,
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "demo"
    assert body["sync"] is not None
    assert body["sync"]["fetched"] == 5


def test_connect_and_import_rejects_manual_upload(client, auth):
    resp = client.post(
        "/api/v1/sources/connectors/manual_upload/connect-and-import",
        json={"allow_demo": True},
        headers=auth,
    )
    assert resp.status_code == 422


def test_seeded_connections_include_a_policy_blocked_source(client, auth):
    conns = client.get("/api/v1/sources/connections", headers=auth).json()
    by_key = {c["connector_key"]: c for c in conns}
    assert by_key["apollo"]["policy_allowed"] is False
    assert by_key["salesforce"]["policy_allowed"] is True


def test_source_sync_creates_leads(client, auth):
    conns = client.get("/api/v1/sources/connections", headers=auth).json()
    hubspot = next(c for c in conns if c["connector_key"] == "hubspot")
    resp = client.post(f"/api/v1/sources/connections/{hubspot['id']}/sync",
                       json={"limit": 8, "reset_cursor": True},
                       headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fetched"] == 8
    # Duplicates are collapsed against what the seed already loaded.
    assert body["created"] + body["duplicates"] == 8


def test_manual_upload_preview_and_ingest(client, auth):
    csv = (
        "Full Name,Job Title,Company,Work Email,City,Industry,Employees\n"
        "Nadia Haddad,Head of Data Platform,Levant Bank,nadia@levantbank.com,Amman,Banking,4200\n"
        "Marcus Bell,Chief Operating Officer,Bell Logistics,marcus@belllogistics.com,Leeds,Software,2600\n"
    )
    files = {"file": ("upload.csv", io.BytesIO(csv.encode()), "text/csv")}
    preview = client.post("/api/v1/sources/upload/preview", files=files, headers=auth)
    assert preview.status_code == 200, preview.text
    assert preview.json()["mapping"]["title"] == "Job Title"

    files = {"file": ("upload.csv", io.BytesIO(csv.encode()), "text/csv")}
    resp = client.post("/api/v1/sources/upload", files=files,
                       data={"mapping_json": json.dumps({}), "run_pipeline": "true"},
                       headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_read"] == 2
    assert body["rows_valid"] == 2
    assert len(body["lead_ids"]) == 2


def test_verification_queue_and_resolution(client, auth):
    queue = client.get("/api/v1/leads/verification/queue", headers=auth).json()
    assert isinstance(queue, list)
    if queue:
        first = queue[0]
        assert first["status"] in ("MISMATCH", "NEEDS_REVIEW")
        resolved = client.post("/api/v1/leads/verification/resolve",
                               json={"verification_id": first["verification_id"],
                                     "resolution": "extracted"},
                               headers=auth)
        assert resolved.status_code == 200

    bulk = client.post("/api/v1/leads/verification/bulk-resolve",
                       json={"resolution": "extracted"}, headers=auth)
    assert bulk.status_code == 200
    assert client.get("/api/v1/leads/verification/queue", headers=auth).json() == []


def test_enrich_and_score_with_custom_weights(client, auth):
    enriched = client.post("/api/v1/leads/enrich", json={}, headers=auth)
    assert enriched.status_code == 200
    body = enriched.json()
    assert body.get("enriched", 0) >= 1 or body.get("items")

    base = client.post("/api/v1/leads/score", json={}, headers=auth).json()
    assert base["items"]

    skewed = client.post("/api/v1/leads/score",
                         json={"weights": {"seniority": 60, "icp_fit": 10,
                                           "industry_fit": 10, "company_size": 5,
                                           "technology_fit": 5, "engagement": 5,
                                           "historical_conversion": 5}},
                         headers=auth).json()
    assert skewed["weights"]["seniority"] == 60


def test_lead_detail_exposes_the_full_decision_trail(client, auth):
    leads = client.get("/api/v1/leads", headers=auth).json()
    assert leads
    detail = None
    for lead in leads[:40]:
        candidate = client.get(f"/api/v1/leads/{lead['id']}", headers=auth).json()
        if candidate.get("enrichment") and candidate.get("extraction"):
            detail = candidate
            break
    assert detail is not None, "expected at least one enriched lead after enrich step"
    assert detail["score_detail"]["factors"]
    assert detail["verifications"] is not None


def test_full_campaign_flow(client, auth):
    segments = client.post("/api/v1/leads/segments",
                           json={"name": "auto", "min_score": 55, "group_by": "persona",
                                 "min_size": 1},
                           headers=auth).json()
    viable = [s for s in segments["segments"] if s["viable"]]
    assert viable, "expected at least one viable segment"
    segment_id = viable[0]["segment_id"]

    docs = client.get("/api/v1/knowledge/documents", headers=auth).json()
    approved_ids = [d["id"] for d in docs if d["approved"]]
    assert approved_ids, "seed should approve at least one document"

    campaign = client.post("/api/v1/campaigns",
                           json={"name": "Q4 verification play",
                                 "objective": "Book discovery calls with leaders who "
                                              "own prospect data quality",
                                 "tone": "Consultative", "segment_id": segment_id,
                                 "knowledge_doc_ids": approved_ids},
                           headers=auth).json()

    planned = client.post(f"/api/v1/campaigns/{campaign['id']}/strategy",
                          headers=auth).json()
    assert planned["strategy"]["sequence"]
    assert planned["strategy"]["cited_documents"]

    generated = client.post(f"/api/v1/campaigns/{campaign['id']}/emails",
                            json={"lead_ids": [], "regenerate": False},
                            headers=auth)
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload["generated"]["count"] > 0
    assert set(payload["compliance"]["verdicts"]) == {
        "APPROVE_FOR_REVIEW", "NEEDS_REVIEW", "BLOCK"}

    emails = client.get("/api/v1/emails", params={"campaign_id": campaign["id"]},
                        headers=auth).json()
    sendable = [e for e in emails if e["compliance"]["verdict"] != "BLOCK"]
    assert sendable

    edited = client.patch(f"/api/v1/emails/{sendable[0]['id']}",
                          json={"body": sendable[0]["body"] + "\n\nP.S. Happy to "
                                                              "share the methodology."},
                          headers=auth).json()
    assert edited["edited_by_human"] is True

    approved = client.post("/api/v1/emails/approve",
                           json={"email_ids": [e["id"] for e in sendable],
                                 "decision": "approved"},
                           headers=auth)
    assert approved.status_code == 200, approved.text

    sent = client.post("/api/v1/emails/send",
                       json={"email_ids": [e["id"] for e in sendable]},
                       headers=auth).json()
    assert sent["sent"] >= 1

    analytics = client.get(f"/api/v1/analytics/campaigns/{campaign['id']}",
                           headers=auth).json()
    assert analytics["funnel"]["sent"] >= 1
    assert "health" in analytics

    lead_id = sendable[0]["lead_id"]
    reply = client.post("/api/v1/replies",
                        json={"lead_id": lead_id, "email_id": sendable[0]["id"],
                              "body": "This is timely. Can you do Thursday afternoon "
                                      "for a call?"},
                        headers=auth).json()
    assert reply["intent"] == "MEETING_REQUEST"
    assert reply["requires_human"] is True

    executed = client.post(f"/api/v1/replies/{reply['id']}/execute",
                           headers=auth).json()
    assert executed["action_status"] == "executed"


def test_blocked_emails_cannot_be_approved(client, auth):
    """Compliance is a hard gate, not a suggestion."""
    emails = client.get("/api/v1/emails", headers=auth).json()
    blocked = [e for e in emails
               if e["compliance"] and e["compliance"]["verdict"] == "BLOCK"]
    if not blocked:
        return  # nothing blocked in this run
    resp = client.post("/api/v1/emails/approve",
                       json={"email_ids": [blocked[0]["id"]], "decision": "approved"},
                       headers=auth)
    assert resp.status_code == 409
    assert resp.json()["error"] == "policy_violation"


def test_unsubscribe_reply_suppresses_the_contact(client, auth):
    leads = client.get("/api/v1/leads", headers=auth).json()
    lead = leads[-1]
    client.post("/api/v1/replies",
                json={"lead_id": lead["id"],
                      "body": "Please remove me from this list and do not contact "
                              "me again."},
                headers=auth)
    suppression = client.get("/api/v1/tenants/suppression", headers=auth).json()
    assert any(entry["email"] == lead["email"] for entry in suppression)


def test_agent_monitor_endpoints(client, auth):
    catalog = client.get("/api/v1/agents/catalog", headers=auth).json()
    assert len(catalog) == 13

    executions = client.get("/api/v1/agents/executions", headers=auth).json()
    assert executions and executions[0]["agent"]

    decisions = client.get("/api/v1/agents/decisions", headers=auth).json()
    assert any(d["human_override"] for d in decisions)

    workflows = client.get("/api/v1/agents/workflows", headers=auth).json()
    assert workflows

    costs = client.get("/api/v1/analytics/costs", headers=auth).json()
    assert costs["by_agent"]

    audit = client.get("/api/v1/agents/audit", headers=auth).json()
    assert any(entry["action"].startswith("email.") for entry in audit)


def test_dashboard_reports_source_breakdown(client, auth):
    dash = client.get("/api/v1/analytics/dashboard", headers=auth).json()
    assert dash["leads"] > 0
    assert set(dash["leads_by_source"]) & {"salesforce", "hubspot", "manual_upload"}


def test_tenant_isolation(client):
    other = client.post("/api/v1/auth/dev-token",
                        json={"email": "admin@northwind.com", "name": "NW Admin",
                              "role": "tenant_admin", "tenant_slug": "northwind"}).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/api/v1/leads", headers=headers).json() == []


def test_read_only_role_cannot_approve(client):
    token = client.post("/api/v1/auth/dev-token",
                        json={"email": "analyst@feuji.com", "name": "An Analyst",
                              "role": "analyst", "tenant_slug": "feuji-revops"}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    resp = client.post("/api/v1/emails/approve",
                       json={"email_ids": ["anything"], "decision": "approved"},
                       headers=headers)
    assert resp.status_code == 403
