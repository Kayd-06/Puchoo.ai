"""Auth API: signup, login, session, logout, CSRF, and rate limits."""

from datetime import timedelta

from fastapi.testclient import TestClient

from backend import database
from backend.emailer import EmailDeliveryError
from backend.main import create_app
from backend.models import AuthSession, EmailChangeCode, InstituteInvite, LoginCode, User
from backend.security import as_utc, decode_session_token, utcnow
from backend.tests.conftest import csrf_headers, finish_login, finish_signup, signup_payload


def _cookie_headers(response) -> str:
    values = response.headers.get_list("set-cookie")
    return "\n".join(values)


def test_signup_sends_code_and_verification_creates_session(client: TestClient, otp_codes):
    response = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email="Ada@College.edu"),
        headers=csrf_headers(client),
    )
    assert response.status_code == 202
    assert response.json() == {"otp_required": True, "email": "ada@college.edu"}
    assert "puchoo_session=" not in _cookie_headers(response)
    assert client.get("/api/v1/auth/me").status_code == 401

    db = database.SessionLocal()
    user = db.query(User).one()
    code = db.query(LoginCode).one()
    db.close()
    assert user.password_hash != "language10"
    assert user.password_hash.startswith("$argon2")
    assert code.code_hash != otp_codes["ada@college.edu"]

    verified = finish_signup(client, "ada@college.edu", otp_codes)
    assert verified.json()["user"]["full_name"] == "Ada Lovelace"
    set_cookie = _cookie_headers(verified)
    assert "puchoo_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    token = client.cookies.get("puchoo_session")
    assert token is not None and token.count(".") == 2
    assert decode_session_token(token) is not None


def test_otp_challenge_does_not_depend_on_chroma_memory(app, otp_codes, monkeypatch):
    """A missing or unavailable conversation store must never block sign-in."""

    def chroma_unavailable():
        raise AssertionError("OTP routes must not initialize ChromaDB")

    # Product routes import this lazily, so patch both consumers before using
    # the full application configuration that production runs.
    monkeypatch.setattr("apps.api.routers.history.get_chat_memory", chroma_unavailable)
    monkeypatch.setattr("apps.api.routers.query.get_chat_memory", chroma_unavailable)

    with TestClient(create_app(include_product=True)) as product_client:
        response = product_client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email="chroma-independent@college.edu"),
            headers=csrf_headers(product_client),
        )

    assert response.status_code == 202
    assert otp_codes["chroma-independent@college.edu"]


def test_duplicate_signup_is_generic(client: TestClient):
    headers = csrf_headers(client)
    first = client.post("/api/v1/auth/signup", json=signup_payload(), headers=headers)
    assert first.status_code == 202

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


def test_refresh_checks_keep_a_stable_valid_session(client: TestClient, otp_codes):
    """Parallel page-load calls must not rotate a browser session out of sync."""
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    finish_signup(client, "ada@college.edu", otp_codes)
    original_token = client.cookies.get("puchoo_session")
    assert original_token

    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.cookies.get("puchoo_session") == original_token
    # A duplicate request carrying the original cookie is equally valid.
    client.cookies.set("puchoo_session", original_token)
    second = client.get("/api/v1/auth/me")
    assert second.status_code == 200
    assert second.json()["email"] == "ada@college.edu"


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


def test_tampered_jwt_cookie_is_rejected(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    finish_signup(client, "ada@college.edu", otp_codes)
    token = client.cookies.get("puchoo_session")
    assert token is not None

    client.cookies.set("puchoo_session", token[:-1] + ("a" if token[-1] != "a" else "b"))
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_email_change_requires_password_and_new_email_otp(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    finish_signup(client, "ada@college.edu", otp_codes)

    wrong_password = client.post(
        "/api/v1/auth/email/change",
        json={"new_email": "ada.new@college.edu", "current_password": "not-the-password"},
        headers=csrf_headers(client),
    )
    assert wrong_password.status_code == 401

    challenge = client.post(
        "/api/v1/auth/email/change",
        json={"new_email": "Ada.New@College.edu", "current_password": "language10"},
        headers=csrf_headers(client),
    )
    assert challenge.status_code == 200
    assert challenge.json() == {"otp_required": True, "email": "ada.new@college.edu"}

    verified = client.post(
        "/api/v1/auth/email/change/verify",
        json={"new_email": "ada.new@college.edu", "code": otp_codes["ada.new@college.edu"]},
        headers=csrf_headers(client),
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["email"] == "ada.new@college.edu"
    assert client.get("/api/v1/auth/me").json()["email"] == "ada.new@college.edu"

    db = database.SessionLocal()
    code = db.query(EmailChangeCode).one()
    db.close()
    assert code.consumed_at is not None


def test_logout_revokes_session_and_clears_cookie(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    finish_signup(client, "ada@college.edu", otp_codes)
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


def test_sliding_session_renewal(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    finish_signup(client, "ada@college.edu", otp_codes)
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
    assert created.status_code == 202
    db = database.SessionLocal()
    user = db.query(User).filter_by(email="inst@college.edu").one()
    db.close()
    assert user.institute_name == "North Campus"
    assert user.workspace_type == "institute"


def test_business_invite_assigns_a_shared_tenant_and_ignores_joiner_type(client: TestClient, otp_codes):
    """A code binds a member to its owner tenant, never to client supplied metadata."""
    owner_payload = signup_payload(
        full_name="Business Owner",
        email="owner@business.com",
        workspace_type="business",
        workspace_name="Northstar Labs",
    )
    assert client.post("/api/v1/auth/signup", json=owner_payload, headers=csrf_headers(client)).status_code == 202
    finish_signup(client, "owner@business.com", otp_codes)
    invite = client.post("/api/v1/auth/workspace/invite", json={"role": "viewer"}, headers=csrf_headers(client))
    assert invite.status_code == 200
    assert invite.json()["role"] == "viewer"

    from backend.main import create_app
    from fastapi.testclient import TestClient as FreshClient
    with FreshClient(create_app(include_product=False)) as member_client:
        member_payload = signup_payload(
            full_name="Business Partner",
            email="partner@business.com",
            workspace_type="institution",  # Must not control tenant assignment.
            workspace_name="Pretend School",
            invite_code=invite.json()["code"],
        )
        joined = member_client.post("/api/v1/auth/signup", json=member_payload, headers=csrf_headers(member_client))
        assert joined.status_code == 202

    db = database.SessionLocal()
    owner = db.query(User).filter_by(email="owner@business.com").one()
    member = db.query(User).filter_by(email="partner@business.com").one()
    db.close()
    assert member.workspace_type == "business"
    assert member.workspace_owner_id == owner.id
    assert member.workspace_role == "viewer"


def test_institution_role_codes_are_independent_and_rotate_only_their_role(client: TestClient, otp_codes):
    """An owner can safely share distinct role codes without cross-role revocation."""
    owner_payload = signup_payload(
        full_name="Institution Owner",
        email="owner@school.edu",
        workspace_type="institution",
        workspace_name="North Campus",
    )
    assert client.post("/api/v1/auth/signup", json=owner_payload, headers=csrf_headers(client)).status_code == 202
    finish_signup(client, "owner@school.edu", otp_codes)

    issued = {}
    for role in ("admin", "editor", "viewer"):
        response = client.post(
            "/api/v1/auth/workspace/invite",
            json={"role": role},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200
        issued[role] = response.json()["code"]
        assert response.json()["role"] == role

    db = database.SessionLocal()
    active = db.query(InstituteInvite).filter_by(revoked_at=None).all()
    assert {invite.role for invite in active} == {"admin", "editor", "viewer"}
    assert len({invite.code_hash for invite in active}) == 3
    db.close()

    rotated = client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "editor"},
        headers=csrf_headers(client),
    )
    assert rotated.status_code == 200
    assert rotated.json()["code"] != issued["editor"]

    db = database.SessionLocal()
    active = db.query(InstituteInvite).filter_by(revoked_at=None).all()
    assert {invite.role for invite in active} == {"admin", "editor", "viewer"}
    assert len(active) == 3
    revoked_editors = db.query(InstituteInvite).filter(InstituteInvite.role == "editor", InstituteInvite.revoked_at.is_not(None)).all()
    assert len(revoked_editors) == 1
    db.close()


def test_workspace_code_on_a_new_client_joins_the_recipient_to_only_that_tenant(client: TestClient, otp_codes):
    """A shared code works across devices after the recipient completes their own OTP."""
    owner_payload = signup_payload(
        full_name="School Admin",
        email="admin@school.edu",
        workspace_type="institution",
        workspace_name="North Campus",
    )
    assert client.post("/api/v1/auth/signup", json=owner_payload, headers=csrf_headers(client)).status_code == 202
    finish_signup(client, "admin@school.edu", otp_codes)
    code_response = client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "viewer"},
        headers=csrf_headers(client),
    )
    assert code_response.status_code == 200

    from backend.main import create_app
    from fastapi.testclient import TestClient as FreshClient

    with FreshClient(create_app(include_product=False)) as recipient_client:
        recipient_payload = signup_payload(
            full_name="Teacher Recipient",
            email="teacher.personal@example.com",
            workspace_type="business",  # The invite, never this value, chooses the tenant.
            workspace_name="Untrusted value",
            invite_code=code_response.json()["code"],
        )
        joined = recipient_client.post(
            "/api/v1/auth/signup",
            json=recipient_payload,
            headers=csrf_headers(recipient_client),
        )
        assert joined.status_code == 202
        verified = finish_signup(recipient_client, "teacher.personal@example.com", otp_codes)
        assert verified.status_code == 200
        identity = recipient_client.get("/api/v1/auth/me")
        assert identity.status_code == 200
        assert identity.json()["email"] == "teacher.personal@example.com"
        assert identity.json()["workspace_type"] == "institution"
        assert identity.json()["workspace_role"] == "viewer"

    db = database.SessionLocal()
    owner = db.query(User).filter_by(email="admin@school.edu").one()
    recipient = db.query(User).filter_by(email="teacher.personal@example.com").one()
    db.close()
    assert recipient.workspace_owner_id == owner.id
    assert recipient.workspace_name == owner.workspace_name


def test_business_role_codes_are_independent_and_rotate_only_their_role(client: TestClient, otp_codes):
    payload = signup_payload(
        full_name="Business Owner",
        email="owner@business.com",
        workspace_type="business",
        workspace_name="Northstar Labs",
    )
    assert client.post("/api/v1/auth/signup", json=payload, headers=csrf_headers(client)).status_code == 202
    finish_signup(client, "owner@business.com", otp_codes)
    issued = {}
    for role in ("admin", "editor", "viewer"):
        invite = client.post(
            "/api/v1/auth/workspace/invite",
            json={"role": role},
            headers=csrf_headers(client),
        )
        assert invite.status_code == 200
        issued[role] = invite.json()["code"]

    rotated = client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "editor"},
        headers=csrf_headers(client),
    )
    assert rotated.status_code == 200
    assert rotated.json()["code"] != issued["editor"]

    db = database.SessionLocal()
    owner = db.query(User).filter_by(email="owner@business.com").one()
    active = db.query(InstituteInvite).filter_by(revoked_at=None).all()
    db.close()
    assert owner.workspace_type == "business"
    assert {invite.role for invite in active} == {"admin", "editor", "viewer"}


def test_resend_replaces_the_previous_otp(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    original = otp_codes["ada@college.edu"]
    response = client.post(
        "/api/v1/auth/login/resend",
        json={"email": "ada@college.edu"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    replacement = otp_codes["ada@college.edu"]
    assert replacement != original
    assert client.post(
        "/api/v1/auth/login/verify",
        json={"email": "ada@college.edu", "code": original},
        headers=csrf_headers(client),
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login/verify",
        json={"email": "ada@college.edu", "code": replacement},
        headers=csrf_headers(client),
    ).status_code == 200


def test_signup_removes_account_when_email_delivery_fails(client: TestClient, monkeypatch):
    def fail_delivery(_to_email: str, _otp_code: str) -> None:
        raise EmailDeliveryError("delivery failed")

    monkeypatch.setattr("backend.emailer.send_otp_email", fail_delivery)
    response = client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    assert response.status_code == 503
    assert response.json()["detail"] == "We could not send the verification email. Try again in a moment."
    db = database.SessionLocal()
    assert db.query(User).count() == 0
    db.close()


def test_single_use_recovery_otp_can_complete_a_password_verified_login(client: TestClient, otp_codes):
    client.post("/api/v1/auth/signup", json=signup_payload(), headers=csrf_headers(client))
    finish_signup(client, "ada@college.edu", otp_codes)

    generated = client.post(
        "/api/v1/auth/recovery-codes",
        json={"current_password": "language10"},
        headers=csrf_headers(client),
    )
    assert generated.status_code == 200
    codes = generated.json()["codes"]
    assert len(codes) == 10
    assert all(code.startswith("PCH-") for code in codes)

    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 200
    challenge = client.post(
        "/api/v1/auth/login",
        json={"email": "ada@college.edu", "password": "language10"},
        headers=csrf_headers(client),
    )
    assert challenge.status_code == 200
    assert challenge.json()["recovery_available"] is True
    verified = client.post(
        "/api/v1/auth/login/verify",
        json={"email": "ada@college.edu", "code": codes[0]},
        headers=csrf_headers(client),
    )
    assert verified.status_code == 200

    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 200
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "ada@college.edu", "password": "language10"},
        headers=csrf_headers(client),
    ).status_code == 200
    reused = client.post(
        "/api/v1/auth/login/verify",
        json={"email": "ada@college.edu", "code": codes[0]},
        headers=csrf_headers(client),
    )
    assert reused.status_code == 401
