"""Auth API: signup, login, session, logout, CSRF, and rate limits."""

from datetime import timedelta

from fastapi.testclient import TestClient

from backend import database
from backend.models import AuthSession, User
from backend.security import as_utc, utcnow
from backend.tests.conftest import csrf_headers, finish_login, signup_payload


def _cookie_headers(response) -> str:
    values = response.headers.get_list("set-cookie")
    return "\n".join(values)


def test_signup_creates_user_and_session(client: TestClient):
    response = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email="Ada@College.edu"),
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    body = response.json()["user"]
    assert body["email"] == "ada@college.edu"
    assert body["full_name"] == "Ada Lovelace"
    assert body["workspace_type"] == "personal"
    assert body["institute_name"] is None
    assert "password" not in body

    set_cookie = _cookie_headers(response)
    assert "puchoo_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    db = database.SessionLocal()
    user = db.query(User).one()
    session = db.query(AuthSession).one()
    db.close()
    assert user.password_hash != "language10"
    assert user.password_hash.startswith("$argon2")
    assert session.token_hash != client.cookies.get("puchoo_session")
    assert session.revoked_at is None


def test_duplicate_signup_is_generic(client: TestClient):
    headers = csrf_headers(client)
    first = client.post("/api/v1/auth/signup", json=signup_payload(), headers=headers)
    assert first.status_code == 201
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    second = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email="ADA@college.edu", full_name="Another Person"),
        headers=csrf_headers(client),
    )
    assert second.status_code == 400
    detail = second.json()["detail"].lower()
    assert detail == "unable to create an account with those details."
    assert "exist" not in detail
    assert "duplicate" not in detail
    assert "registered" not in detail
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_success_and_me(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(email="Ada@College.edu"), headers=csrf_headers(client))
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert client.get("/api/v1/auth/me").status_code == 401

    response = finish_login(client, "ada@college.edu", "language10", otp_codes)
    assert response.json()["user"]["email"] == "ada@college.edu"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["full_name"] == "Ada Lovelace"
    assert me.json()["workspace_type"] == "personal"


def test_wrong_otp_does_not_create_a_session(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    challenged = client.post(
        "/api/v1/auth/login",
        json={"email": "ada@college.edu", "password": "language10"},
        headers=csrf_headers(client),
    )
    assert challenged.status_code == 200
    sent = otp_codes["ada@college.edu"]
    wrong_code = "111111" if sent == "000000" else "000000"
    wrong = client.post(
        "/api/v1/auth/login/verify",
        json={"email": "ada@college.edu", "code": wrong_code},
        headers=csrf_headers(client),
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "That code is invalid or has expired."
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_failure_is_generic(client: TestClient):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@college.edu", "password": "language10"},
        headers=csrf_headers(client),
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "ada@college.edu", "password": "wrongpassword1"},
        headers=csrf_headers(client),
    )
    assert unknown.status_code == 401
    assert wrong.status_code == 401
    assert unknown.json()["detail"] == "Invalid email or password"
    assert wrong.json()["detail"] == "Invalid email or password"
    assert "puchoo_session" not in client.cookies
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_without_session(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_logout_revokes_session_and_clears_cookie(client: TestClient):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    raw_token = client.cookies.get("puchoo_session")
    assert raw_token

    response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert client.cookies.get("puchoo_session") in {None, ""}
    assert client.get("/api/v1/auth/me").status_code == 401

    db = database.SessionLocal()
    session = db.query(AuthSession).one()
    revoked = session.revoked_at is not None
    db.close()
    assert revoked

    with TestClient(client.app) as reused:
        reused.cookies.set("puchoo_session", raw_token)
        assert reused.get("/api/v1/auth/me").status_code == 401


def test_csrf_rejection(client: TestClient):
    missing = client.post("/api/v1/auth/signup", json=signup_payload())
    assert missing.status_code == 403
    assert missing.json()["detail"] == "CSRF token missing or invalid"

    client.get("/api/v1/auth/csrf")
    mismatched = client.post(
        "/api/v1/auth/login",
        json={"email": "ada@college.edu", "password": "language10"},
        headers={"X-CSRF-Token": "not-the-cookie"},
    )
    assert mismatched.status_code == 403


def test_login_rate_limit_per_ip(app):
    with TestClient(app, client=("203.0.113.10", 5000)) as limited:
        headers = csrf_headers(limited)
        for index in range(5):
            response = limited.post(
                "/api/v1/auth/login",
                json={"email": f"person{index}@college.edu", "password": "language10"},
                headers=headers,
            )
            assert response.status_code == 401
        blocked = limited.post(
            "/api/v1/auth/login",
            json={"email": "someoneelse@college.edu", "password": "language10"},
            headers=headers,
        )
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "900"


def test_signup_rate_limit_per_email(app):
    email = "limited@college.edu"
    last = None
    for index in range(6):
        with TestClient(app, client=(f"198.51.100.{index + 1}", 5000)) as visitor:
            last = visitor.post(
                "/api/v1/auth/signup",
                json=signup_payload(email=email, full_name=f"Person {index}"),
                headers=csrf_headers(visitor),
            )
    assert last is not None
    assert last.status_code == 429


def test_sliding_session_renewal(client: TestClient):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    soon = utcnow() + timedelta(minutes=5)
    db = database.SessionLocal()
    record = db.query(AuthSession).one()
    record.expires_at = soon
    db.commit()
    db.close()

    assert client.get("/api/v1/auth/me").status_code == 200
    db = database.SessionLocal()
    record = db.query(AuthSession).one()
    renewed = as_utc(record.expires_at)
    db.close()
    assert renewed > soon + timedelta(days=6)


def test_institute_signup_requires_name(client: TestClient):
    missing = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(workspace_type="institute", email="inst@college.edu"),
        headers=csrf_headers(client),
    )
    assert missing.status_code == 422

    created = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(
            workspace_type="institute",
            institute_name="North Campus",
            email="inst@college.edu",
        ),
        headers=csrf_headers(client),
    )
    assert created.status_code == 201
    assert created.json()["user"]["institute_name"] == "North Campus"
    assert created.json()["user"]["workspace_type"] == "institute"
