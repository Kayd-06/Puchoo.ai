"""Server connection routes reject injection, editors, and raw driver errors."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from apps.api.session import session_manager
from apps.core.db_connection import SecretValue
from apps.core.workspaces import Workspace
from backend.main import create_app
from backend.rate_limit import connection_limiter
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload

GENERIC = "Could not connect to the database"
PASSWORD = "s3cret-db-password"


def _body(**overrides):
    payload = {
        "name": "Reporting",
        "engine": "postgresql",
        "host": "db.example.com",
        "port": 5432,
        "database": "reporting",
        "username": "readonly",
        "password": PASSWORD,
        "ssl_required": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def owner_client(app, otp_codes):
    with TestClient(create_app(include_product=True)) as test_client:
        created = test_client.post(
            "/api/v1/auth/signup",
            json=signup_payload(workspace_type="business", workspace_name="Northstar"),
            headers=csrf_headers(test_client),
        )
        assert created.status_code == 202
        finish_signup(test_client, "ada@college.edu", otp_codes)
        yield test_client


def test_injected_connection_fields_are_rejected(owner_client: TestClient):
    cases = [
        {"database": "prod?local_infile=1"},
        {"database": "db#"},
        {"database": "prod%3F"},
        {"host": "x@evil:3306"},
        {"host": "db.example.com%3F"},
        {"username": "root?local_infile=1"},
        {"port": "5432"},
        {"port": True},
        {"port": 0},
        {"port": 70000},
    ]
    for overrides in cases:
        response = owner_client.post(
            "/api/workspaces/server",
            json=_body(**overrides),
            headers=csrf_headers(owner_client),
        )
        assert response.status_code == 422, overrides
        assert isinstance(response.json()["detail"], str)
        assert "local_infile" not in response.text
        assert PASSWORD not in response.text
        assert "DRIVER_TOKEN" not in response.text


def test_editor_cannot_add_a_connection_and_admin_can(owner_client, otp_codes, monkeypatch):
    editor_invite = owner_client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "editor"},
        headers=csrf_headers(owner_client),
    )
    admin_invite = owner_client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "admin"},
        headers=csrf_headers(owner_client),
    )
    assert editor_invite.status_code == 200
    assert admin_invite.status_code == 200

    def forbidden(*_args, **_kwargs):
        raise AssertionError("an editor must not open a database connection")

    monkeypatch.setattr("apps.api.routers.workspaces.create_server_workspace", forbidden)
    with TestClient(owner_client.app) as editor:
        joined = editor.post(
            "/api/v1/auth/signup",
            json=signup_payload(email="editor@college.edu", full_name="Ed Itor", invite_code=editor_invite.json()["code"]),
            headers=csrf_headers(editor),
        )
        assert joined.status_code == 202
        finish_signup(editor, "editor@college.edu", otp_codes)
        denied = editor.post("/api/workspaces/server", json=_body(), headers=csrf_headers(editor))
        assert denied.status_code == 403

    def allowed(name, **kwargs):
        return Workspace(
            id="ws_admin",
            name=name,
            database_uri="postgresql+psycopg://readonly@8.8.8.8:5432/reporting",
            dialect="postgresql",
            source_type="server",
            connect_args={"password": SecretValue(kwargs["password"]), "sslmode": "require"},
        )

    monkeypatch.setattr("apps.api.routers.workspaces.create_server_workspace", allowed)
    try:
        with TestClient(owner_client.app) as admin:
            joined = admin.post(
                "/api/v1/auth/signup",
                json=signup_payload(email="admin@college.edu", full_name="Ad Min", invite_code=admin_invite.json()["code"]),
                headers=csrf_headers(admin),
            )
            assert joined.status_code == 202
            finish_signup(admin, "admin@college.edu", otp_codes)
            connected = admin.post("/api/workspaces/server", json=_body(), headers=csrf_headers(admin))
            assert connected.status_code == 200
            assert connected.json()["source_type"] == "server"
            assert PASSWORD not in connected.text
            assert "database_uri" not in connected.json()
            assert "8.8.8.8" not in connected.text
    finally:
        session_manager.workspaces.pop("ws_admin", None)


def test_connection_attempts_are_rate_limited(owner_client, monkeypatch):
    connection_limiter.reset()
    monkeypatch.setattr("apps.core.workspaces.checked_connection_host", lambda host, port: "8.8.8.8")

    def explode(*_args, **_kwargs):
        raise OperationalError("CONNECT", {}, Exception(f"DRIVER_TOKEN password={PASSWORD}"))

    monkeypatch.setattr("apps.core.workspaces.get_schema_snapshot", explode)
    for _ in range(5):
        failed = owner_client.post("/api/workspaces/server", json=_body(), headers=csrf_headers(owner_client))
        assert failed.status_code == 400
        assert failed.json()["detail"] == GENERIC
        assert PASSWORD not in failed.text
        assert "DRIVER_TOKEN" not in failed.text
        assert "local_infile" not in failed.text
    blocked = owner_client.post("/api/workspaces/server", json=_body(), headers=csrf_headers(owner_client))
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many connection attempts. Try again later."
    assert blocked.headers["retry-after"] == "900"


def test_http_connection_errors_hide_driver_text(owner_client, monkeypatch, caplog):
    connection_limiter.reset()
    monkeypatch.setattr("apps.core.workspaces.checked_connection_host", lambda host, port: "8.8.8.8")

    def explode(*_args, **_kwargs):
        raise OperationalError("CONNECT", {}, Exception(f"DRIVER_TOKEN password={PASSWORD} local_infile=1"))

    monkeypatch.setattr("apps.core.workspaces.get_schema_snapshot", explode)
    with caplog.at_level(logging.WARNING):
        failed = owner_client.post("/api/workspaces/server", json=_body(host="127.0.0.1"), headers=csrf_headers(owner_client))
    assert failed.status_code == 400
    assert failed.json()["detail"] == GENERIC
    assert PASSWORD not in failed.text
    assert "DRIVER_TOKEN" not in failed.text
    assert "local_infile" not in failed.text
    assert PASSWORD not in caplog.text
