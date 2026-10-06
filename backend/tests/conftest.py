"""Isolated SQLite database and a clean rate-limit window for each test."""

import sys
import types

import pytest
from fastapi.testclient import TestClient

# Chroma imports the OTLP gRPC exporter at startup. That native module is
# optional telemetry, and some Windows code-integrity policies block it.
# The app disables Chroma telemetry, so tests can load the local client
# without the blocked exporter.
if "opentelemetry.exporter.otlp.proto.grpc.trace_exporter" not in sys.modules:
    _otlp_grpc = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
    _otlp_grpc.OTLPSpanExporter = object
    sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = _otlp_grpc

from backend.database import configure_database, init_db
from backend.emailer import EmailDeliveryError
from backend.main import create_app
from backend.rate_limit import connection_limiter, limiter


@pytest.fixture(autouse=True)
def block_outbound_smtp(monkeypatch):
    """The suite must not log into the SMTP account configured in .env."""

    def refuse(*_args, **_kwargs):
        raise EmailDeliveryError("SMTP is disabled during tests")

    monkeypatch.setattr("backend.emailer.smtplib.SMTP", refuse)
    monkeypatch.setattr("backend.emailer.smtplib.SMTP_SSL", refuse)


@pytest.fixture
def app(tmp_path):
    configure_database("sqlite:///" + (tmp_path / "auth.db").as_posix())
    init_db()
    limiter.reset()
    connection_limiter.reset()
    return create_app(include_product=False)


class CapturedCodes(dict):
    def __init__(self) -> None:
        super().__init__()
        self.notices: list[str] = []


@pytest.fixture
def otp_codes(monkeypatch):
    sent = CapturedCodes()

    def capture(to_email: str, otp_code: str) -> None:
        sent[to_email] = otp_code

    def capture_notice(to_email: str) -> None:
        sent.notices.append(to_email)

    monkeypatch.setattr("backend.emailer.send_otp_email", capture)
    monkeypatch.setattr("backend.emailer.send_email_changed_notice", capture_notice)
    return sent


@pytest.fixture
def client(app, otp_codes):
    with TestClient(app) as test_client:
        yield test_client


def csrf_headers(test_client: TestClient) -> dict[str, str]:
    response = test_client.get("/api/v1/auth/csrf")
    assert response.status_code == 204
    token = test_client.cookies.get("csrf_token")
    assert token
    return {"X-CSRF-Token": token}


def finish_login(test_client: TestClient, email: str, password: str, otp_codes: dict[str, str]):
    challenged = test_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(test_client),
    )
    assert challenged.status_code == 200
    assert challenged.json()["otp_required"] is True
    assert test_client.get("/api/v1/auth/me").status_code == 401
    verified = test_client.post(
        "/api/v1/auth/login/verify",
        json={"email": email, "code": otp_codes[email.lower()]},
        headers=csrf_headers(test_client),
    )
    assert verified.status_code == 200
    return verified


def finish_signup(test_client: TestClient, email: str, otp_codes: dict[str, str]):
    verified = test_client.post(
        "/api/v1/auth/login/verify",
        json={"email": email, "code": otp_codes[email.lower()]},
        headers=csrf_headers(test_client),
    )
    assert verified.status_code == 200
    return verified


def signup_payload(**overrides):
    payload = {
        "full_name": "Ada Lovelace",
        "email": "ada@college.edu",
        "password": "language10",
        "confirm_password": "language10",
        "workspace_type": "personal",
    }
    payload.update(overrides)
    return payload
