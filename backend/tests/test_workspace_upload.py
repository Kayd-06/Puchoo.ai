"""End-to-end upload checks, including credential-redaction guarantees."""

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from uuid import uuid4

from apps.api.session import session_manager
from apps.api.routers import workspaces as workspace_router
from apps.core import workspaces as workspace_core
from backend.main import create_app
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload


def test_csv_validation_accepts_utf8_split_at_the_8kib_sniff_boundary():
    """A valid CSV stays valid when the sniffer cuts through a UTF-8 character."""

    prefix = b"column\n" + (b"x" * (8191 - len(b"column\n")))
    contents = prefix + b"\xc3\xb1\n"

    assert len(prefix) == 8191
    assert workspace_router._validated_upload_kind("boundary.csv", contents) == ".csv"


@pytest.mark.parametrize(
    ("filename", "contents"),
    [
        ("archive.zip", b"PK\x03\x04not-a-workbook"),
        ("workspace.db", b"SQLite format 3\x00\x00\x01"),
    ],
)
def test_upload_validation_rejects_zip_and_sqlite_files(filename, contents):
    """Only CSV and Excel files can create an uploaded workspace."""

    with pytest.raises(HTTPException, match="Unsupported file format"):
        workspace_router._validated_upload_kind(filename, contents)


def test_owner_can_upload_csv_and_workspace_api_never_returns_database_uri(tmp_path, monkeypatch, otp_codes):
    """A successful upload is queryable server-side but hides its local path."""

    monkeypatch.setattr(workspace_core, "LOCAL_WORKSPACE_DIRECTORY", tmp_path)
    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)

    with TestClient(create_app(include_product=True)) as client:
        email = f"owner-{uuid4().hex}@uploadtest.com"
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


def test_editor_cannot_upload_data_sources(client, otp_codes):
    owner_email = "upload-owner@example.com"
    assert client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email=owner_email, workspace_type="business", workspace_name="Acme"),
        headers=csrf_headers(client),
    ).status_code == 202
    finish_signup(client, owner_email, otp_codes)
    invite = client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "editor"},
        headers=csrf_headers(client),
    ).json()["code"]

    with TestClient(create_app(include_product=True)) as editor:
        email = "upload-editor@example.com"
        assert editor.post(
            "/api/v1/auth/signup",
            json=signup_payload(email=email, invite_code=invite),
            headers=csrf_headers(editor),
        ).status_code == 202
        finish_signup(editor, email, otp_codes)

        denied = editor.post(
            "/api/workspaces/upload",
            files={"file": ("report.csv", b"month,total\nJan,4\n", "text/csv")},
            headers=csrf_headers(editor),
        )

        assert denied.status_code == 403


def test_upload_rejects_oversized_or_forged_spreadsheets(monkeypatch, otp_codes):
    """The content signature and a configured byte limit are enforced before parsing."""

    monkeypatch.setattr(workspace_router, "MAX_UPLOAD_BYTES", 32)
    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)

    with TestClient(create_app(include_product=True)) as client:
        email = f"owner-{uuid4().hex}@uploadlimit.com"
        assert client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email=email),
            headers=csrf_headers(client),
        ).status_code == 202
        finish_signup(client, email, otp_codes)

        forged = client.post(
            "/api/workspaces/upload",
            files={"file": ("report.csv", b"<html>not a spreadsheet</html>", "text/csv")},
            headers=csrf_headers(client),
        )
        assert forged.status_code == 400
        assert forged.json()["detail"] == "The uploaded file content does not match its declared format."

        oversized = client.post(
            "/api/workspaces/upload",
            files={"file": ("report.csv", b"column\n" + (b"x" * 40), "text/csv")},
            headers=csrf_headers(client),
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"] == "The uploaded file is too large."


@pytest.mark.parametrize(("count", "expected"), [(10, 200), (11, 400)])
def test_upload_batch_allows_ten_files_and_rejects_eleven(monkeypatch, otp_codes, count, expected):
    """The default batch limit permits ten files and rejects more."""

    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)

    with TestClient(create_app(include_product=True)) as client:
        email = f"owner-{uuid4().hex}@uploadbatch.com"
        assert client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email=email),
            headers=csrf_headers(client),
        ).status_code == 202
        finish_signup(client, email, otp_codes)

        uploaded = client.post(
            "/api/workspaces/upload-multiple",
            files=[
                ("files", (f"report-{number}.csv", b"month,total\nJan,4\n", "text/csv"))
                for number in range(count)
            ],
            headers=csrf_headers(client),
        )

        assert uploaded.status_code == expected
        if expected == 200:
            assert uploaded.json()["source_type"] == "spreadsheet_collection"
