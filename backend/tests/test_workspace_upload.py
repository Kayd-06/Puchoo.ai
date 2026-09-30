"""End-to-end upload checks, including credential-redaction guarantees."""

from fastapi.testclient import TestClient

from apps.api.session import session_manager
from apps.core import workspaces as workspace_core
from backend.main import create_app
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload


def test_owner_can_upload_csv_and_workspace_api_never_returns_database_uri(tmp_path, monkeypatch, otp_codes):
    """A successful upload is queryable server-side but hides its local path."""

    monkeypatch.setattr(workspace_core, "LOCAL_WORKSPACE_DIRECTORY", tmp_path)
    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)

    with TestClient(create_app(include_product=True)) as client:
        email = "owner@uploadtest.com"
        assert client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email=email),
            headers=csrf_headers(client),
        ).status_code == 202
        finish_signup(client, email, otp_codes)

        uploaded = client.post(
            "/api/workspaces/upload",
            data={"name": "Quarterly revenue"},
            files={"file": ("revenue.csv", b"month,revenue\nJan,120\nFeb,160\n", "text/csv")},
            headers=csrf_headers(client),
        )
        assert uploaded.status_code == 200
        workspace = uploaded.json()
        assert workspace["name"] == "Quarterly revenue"
        assert workspace["source_type"] == "spreadsheet"
        assert "database_uri" not in workspace
        assert "owner_user_id" not in workspace

        listed = client.get("/api/workspaces/")
        assert listed.status_code == 200
        assert any(item["id"] == workspace["id"] for item in listed.json())
        assert all("database_uri" not in item for item in listed.json())

        details = client.get(f"/api/workspaces/{workspace['id']}")
        assert details.status_code == 200
        assert "database_uri" not in details.json()

        schema = client.get(f"/api/workspaces/{workspace['id']}/schema")
        assert schema.status_code == 200
        assert "Table: revenue" in schema.json()["schema"]

    session_manager.workspaces.pop(workspace["id"], None)
    session_manager.workspace_guardrails.pop(workspace["id"], None)
    session_manager.query_history.pop(workspace["id"], None)
    session_manager.active_proposals.pop(workspace["id"], None)
    session_manager.schema_snapshots.pop(f"schema_{workspace['id']}", None)
