"""Password-proven login challenges. An email alone cannot start or finish login."""

import asyncio
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import database
from backend.config import ensure_production_secrets
from backend.models import AuthSession, LoginChallenge
from backend.rate_limit import limiter
from backend.security import hash_otp, hash_token, utcnow
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload

LOGIN_EXPIRED = "Login session expired, please sign in again"
INVALID_CODE = "That code is invalid or has expired."
RESEND_COOLDOWN = "Please wait before requesting another code."
RESEND_LIMIT = "Too many codes were sent. Check your email for the latest code or sign in again."


def _cookie_headers(response) -> str:
    return "\n".join(response.headers.get_list("set-cookie"))


def _challenge_cookie(response) -> str:
    for line in response.headers.get_list("set-cookie"):
        if line.lower().startswith("puchoo_login_challenge="):
            return line
    return ""


def _signup(client: TestClient) -> None:
    created = client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    assert created.status_code == 202


def _login(client: TestClient, password: str = "language10", email: str = "ada@college.edu"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )


def _verify(client: TestClient, code: str, email: str = "ada@college.edu"):
    return client.post(
        "/api/v1/auth/login/verify",
        json={"email": email, "code": code},
        headers=csrf_headers(client),
    )


def _resend(client: TestClient, email: str | None = None):
    body = {} if email is None else {"email": email}
    return client.post("/api/v1/auth/login/resend", json=body, headers=csrf_headers(client))


def _wrong_code(sent: str) -> str:
    return "111111" if sent != "111111" else "222222"


def _prepare_login(client: TestClient, otp_codes) -> tuple[str, str]:
    _signup(client)
    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 200
    challenged = _login(client)
    assert challenged.status_code == 200
    challenge_id = client.cookies.get("puchoo_login_challenge")
    assert challenge_id
    return challenge_id, otp_codes["ada@college.edu"]


def test_login_challenge_cookie_is_http_only_and_absent_from_json(client: TestClient, otp_codes, monkeypatch):
    monkeypatch.setattr("backend.security.settings.cookie_secure", False)
    _signup(client)
    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 200
    challenged = _login(client)
    assert challenged.status_code == 200
    assert challenged.json() == {"otp_required": True, "email": "ada@college.edu"}
    assert "email_delivered" not in challenged.text
    assert "recovery_available" not in challenged.text
    cookie = _challenge_cookie(challenged)
    challenge_id = client.cookies.get("puchoo_login_challenge")
    assert challenge_id
    assert challenge_id not in challenged.text
    assert "puchoo_login_challenge=" in cookie
    assert "httponly" in cookie.lower()
    assert "samesite=strict" in cookie.lower()
    assert "max-age=300" in cookie.lower()
    assert "secure" not in cookie.lower()

    monkeypatch.setattr("backend.security.settings.cookie_secure", True)
    client.cookies.delete("puchoo_login_challenge")
    again = _login(client)
    secure_cookie = _challenge_cookie(again)
    assert "secure" in secure_cookie.lower()
    assert again.json().keys() == {"otp_required", "email"}
    secure_id = secure_cookie.split(";", 1)[0].split("=", 1)[1]
    assert secure_id not in again.text


def test_passwordless_resend_and_verify_without_cookie_fail(client: TestClient, otp_codes):
    challenge_id, sent = _prepare_login(client, otp_codes)
    client.cookies.delete("puchoo_login_challenge")

    known = _resend(client, "ada@college.edu")
    unknown = _resend(client, "nobody@college.edu")
    assert known.status_code == unknown.status_code == 400
    assert known.json() == unknown.json() == {"detail": LOGIN_EXPIRED}
    assert otp_codes["ada@college.edu"] == sent

    without_cookie = _verify(client, sent)
    assert without_cookie.status_code == 400
    assert without_cookie.json()["detail"] == LOGIN_EXPIRED
    assert client.get("/api/v1/auth/me").status_code == 401

    client.cookies.set("puchoo_login_challenge", challenge_id)
    restored = _verify(client, sent)
    assert restored.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_correct_password_and_otp_then_reuse_and_expiry(client: TestClient, otp_codes):
    challenge_id, sent = _prepare_login(client, otp_codes)
    db = database.SessionLocal()
    stored = db.get(LoginChallenge, challenge_id)
    assert stored.code_hash == hash_otp(sent)
    assert stored.code_hash != hash_token(sent)
    assert stored.expires_at - stored.created_at == timedelta(minutes=5)
    db.close()

    verified = _verify(client, sent)
    assert verified.status_code == 200
    assert client.cookies.get("puchoo_login_challenge") in {None, ""}
    reused = _verify(client, sent)
    assert reused.status_code == 400
    assert reused.json()["detail"] == LOGIN_EXPIRED

    client.cookies.set("puchoo_login_challenge", challenge_id)
    still_used = _verify(client, sent)
    assert still_used.status_code == 400

    client.cookies.clear()
    second_id, second_code = _prepare_login(client, otp_codes)
    db = database.SessionLocal()
    row = db.get(LoginChallenge, second_id)
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    db.close()
    expired = _verify(client, second_code)
    assert expired.status_code == 400
    assert expired.json()["detail"] == LOGIN_EXPIRED
    assert client.get("/api/v1/auth/me").status_code == 401


def test_five_wrong_attempts_lock_the_challenge(client: TestClient, otp_codes):
    challenge_id, sent = _prepare_login(client, otp_codes)
    wrong = _wrong_code(sent)
    for _ in range(4):
        failed = _verify(client, wrong)
        assert failed.status_code == 401
        assert failed.json()["detail"] == INVALID_CODE
    locked = _verify(client, wrong)
    assert locked.status_code == 400
    assert locked.json()["detail"] == LOGIN_EXPIRED

    client.cookies.set("puchoo_login_challenge", challenge_id)
    sixth = _verify(client, sent)
    assert sixth.status_code == 400
    assert sixth.json()["detail"] == LOGIN_EXPIRED

    db = database.SessionLocal()
    row = db.get(LoginChallenge, challenge_id)
    attempts = row.attempts
    is_locked = row.locked_at is not None
    db.close()
    assert attempts == 5
    assert is_locked
    assert client.get("/api/v1/auth/me").status_code == 401


def test_parallel_wrong_attempts_cannot_pass_the_lock(app, otp_codes):
    original_limit = limiter.limit
    limiter.limit = 100
    try:
        with TestClient(app) as client:
            challenge_id, sent = _prepare_login(client, otp_codes)
            csrf = client.cookies.get("csrf_token")
        wrong = _wrong_code(sent)

        async def flood() -> list[int]:
            transport = httpx.ASGITransport(app=app)

            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
                async def once() -> int:
                    response = await http.post(
                        "/api/v1/auth/login/verify",
                        json={"email": "ada@college.edu", "code": wrong},
                        headers={"X-CSRF-Token": csrf},
                        cookies={"csrf_token": csrf, "puchoo_login_challenge": challenge_id},
                    )
                    return response.status_code

                return list(await asyncio.gather(*[once() for _ in range(8)]))

        statuses = asyncio.run(flood())
        assert len(statuses) == 8
        assert set(statuses) <= {400, 401}
        db = database.SessionLocal()
        row = db.get(LoginChallenge, challenge_id)
        attempts = row.attempts
        is_locked = row.locked_at is not None
        sessions = db.query(AuthSession).filter(AuthSession.revoked_at.is_(None)).count()
        db.close()
        assert attempts == 5
        assert is_locked
        assert sessions == 0
    finally:
        limiter.limit = original_limit


def test_resend_enforces_cooldown_and_limit(client: TestClient, otp_codes):
    _prepare_login(client, otp_codes)
    original = otp_codes["ada@college.edu"]
    cooling = _resend(client, "someone-else@college.edu")
    assert cooling.status_code == 429
    assert cooling.json()["detail"] == RESEND_COOLDOWN
    assert cooling.headers["retry-after"] == "60"
    assert otp_codes["ada@college.edu"] == original

    for _ in range(3):
        db = database.SessionLocal()
        row = db.query(LoginChallenge).filter(LoginChallenge.consumed_at.is_(None)).one()
        row.last_sent_at = utcnow() - timedelta(seconds=61)
        db.commit()
        db.close()
        sent = _resend(client)
        assert sent.status_code == 200
        assert sent.json() == {"otp_required": True, "email": "ada@college.edu"}
        assert "puchoo_login_challenge" not in sent.text

    db = database.SessionLocal()
    row = db.query(LoginChallenge).filter(LoginChallenge.consumed_at.is_(None)).one()
    row.last_sent_at = utcnow() - timedelta(seconds=61)
    db.commit()
    db.close()
    blocked = _resend(client)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == RESEND_LIMIT
    assert blocked.json()["detail"] != LOGIN_EXPIRED
    latest = otp_codes["ada@college.edu"]
    assert latest != original
    assert _verify(client, original).status_code == 401
    assert _verify(client, latest).status_code == 200


def test_login_responses_match_for_real_and_unknown_emails(client: TestClient, otp_codes):
    _signup(client)
    client.cookies.delete("puchoo_login_challenge")
    unknown = _login(client, email="missing@college.edu")
    wrong = _login(client, password="wrongpassword1")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Invalid email or password"}
    assert _challenge_cookie(unknown) == ""
    assert _challenge_cookie(wrong) == ""
    assert "puchoo_login_challenge" not in client.cookies

    logged_out = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logged_out.status_code == 200
    known_resend = _resend(client, "ada@college.edu")
    unknown_resend = _resend(client, "missing@college.edu")
    assert known_resend.status_code == unknown_resend.status_code == 400
    assert known_resend.json() == unknown_resend.json() == {"detail": LOGIN_EXPIRED}


def test_password_reset_revokes_sessions_and_challenges(client: TestClient, otp_codes):
    _signup(client)
    finish_signup(client, "ada@college.edu", otp_codes)
    raw_token = client.cookies.get("puchoo_session")
    assert raw_token
    challenged = _login(client)
    assert challenged.status_code == 200
    challenge_id = client.cookies.get("puchoo_login_challenge")

    forgot = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "ada@college.edu"},
        headers=csrf_headers(client),
    )
    assert forgot.status_code == 200
    reset = client.post(
        "/api/v1/auth/password/reset",
        json={
            "email": "ada@college.edu",
            "code": otp_codes["ada@college.edu"],
            "password": "newlanguage10",
            "confirm_password": "newlanguage10",
        },
        headers=csrf_headers(client),
    )
    assert reset.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401

    with TestClient(client.app) as reused:
        reused.cookies.set("puchoo_session", raw_token)
        assert reused.get("/api/v1/auth/me").status_code == 401

    db = database.SessionLocal()
    challenge = db.get(LoginChallenge, challenge_id)
    consumed = challenge.consumed_at is not None and challenge.locked_at is not None
    active_sessions = db.query(AuthSession).filter(AuthSession.revoked_at.is_(None)).count()
    db.close()
    assert consumed
    assert active_sessions == 0

    assert _login(client, password="language10").status_code == 401
    assert _login(client, password="newlanguage10").status_code == 200


def test_recovery_code_requires_the_password_step(client: TestClient, otp_codes):
    _signup(client)
    finish_signup(client, "ada@college.edu", otp_codes)
    generated = client.post(
        "/api/v1/auth/recovery-codes",
        json={"current_password": "language10"},
        headers=csrf_headers(client),
    )
    assert generated.status_code == 200
    recovery = generated.json()["codes"][0]
    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 200

    skipped = _verify(client, recovery)
    assert skipped.status_code == 400
    assert skipped.json()["detail"] == LOGIN_EXPIRED
    assert client.get("/api/v1/auth/me").status_code == 401

    challenged = _login(client)
    assert challenged.status_code == 200
    assert "recovery_available" not in challenged.json()
    verified = _verify(client, recovery)
    assert verified.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_email_change_revokes_sessions_and_notifies_the_old_address(client: TestClient, otp_codes):
    _signup(client)
    finish_signup(client, "ada@college.edu", otp_codes)
    previous = client.cookies.get("puchoo_session")
    challenged = _login(client)
    assert challenged.status_code == 200
    challenge_id = client.cookies.get("puchoo_login_challenge")

    requested = client.post(
        "/api/v1/auth/email/change",
        json={"new_email": "ada.new@college.edu", "current_password": "language10"},
        headers=csrf_headers(client),
    )
    assert requested.status_code == 200
    verified = client.post(
        "/api/v1/auth/email/change/verify",
        json={"new_email": "ada.new@college.edu", "code": otp_codes["ada.new@college.edu"]},
        headers=csrf_headers(client),
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["email"] == "ada.new@college.edu"
    assert otp_codes.notices == ["ada@college.edu"]
    assert client.get("/api/v1/auth/me").json()["email"] == "ada.new@college.edu"

    with TestClient(client.app) as reused:
        reused.cookies.set("puchoo_session", previous)
        assert reused.get("/api/v1/auth/me").status_code == 401

    db = database.SessionLocal()
    challenge = db.get(LoginChallenge, challenge_id)
    closed = challenge.consumed_at is not None and challenge.locked_at is not None
    db.close()
    assert closed


def test_production_refuses_default_secrets():
    with pytest.raises(RuntimeError, match="SESSION_SECRET and OTP_SECRET"):
        ensure_production_secrets("production", "  ", None)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        ensure_production_secrets("production", "dev-secret-key-do-not-use-in-prod", "unique-otp-secret")
    with pytest.raises(RuntimeError, match="OTP_SECRET"):
        ensure_production_secrets("Production", "unique-session-secret", " ChangeMe ")
    with pytest.raises(RuntimeError, match="OTP_SECRET"):
        ensure_production_secrets("production", "unique-session-secret", "replace-with-a-long-random-string")
    ensure_production_secrets("development", "changeme", "changeme")
    ensure_production_secrets("production", "unique-session-secret", "unique-otp-secret")
