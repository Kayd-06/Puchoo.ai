"""Existing invite-code collaboration must expire and revoke access safely."""

from datetime import timedelta

from fastapi.testclient import TestClient

from backend import database
from backend.models import InstituteInvite, User
from backend.security import utcnow
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload


def _create_owner_and_invite(client, otp_codes, *, role="editor"):
    owner_email = "owner@northstar.com"
    response = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(
            full_name="Northstar Owner",
            email=owner_email,
            workspace_type="business",
            workspace_name="Northstar",
        ),
        headers=csrf_headers(client),
    )
    assert response.status_code == 202
    finish_signup(client, owner_email, otp_codes)
    invite = client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": role},
        headers=csrf_headers(client),
    )
    assert invite.status_code == 200
    return owner_email, invite.json()["code"]


def test_expired_workspace_invite_cannot_join_a_tenant(client, otp_codes):
    """Removing the expiry check would allow old leaked role codes to grant access."""

    _owner_email, code = _create_owner_and_invite(client, otp_codes)
    db = database.SessionLocal()
    try:
        invite = db.query(InstituteInvite).one()
        invite.expires_at = utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    joined = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(email="expired-invite@northstar.com", invite_code=code),
        headers=csrf_headers(client),
    )

    assert joined.status_code == 400
    assert joined.json()["detail"] == "That workspace invite code is invalid."


def test_owner_can_change_member_role_and_removed_member_loses_session(client, otp_codes):
    """Removing either role authorization or session revocation breaks tenant safety."""

    _owner_email, code = _create_owner_and_invite(client, otp_codes)
    with TestClient(client.app) as member_client:
        joined = member_client.post(
            "/api/v1/auth/signup",
            json=signup_payload(
                full_name="Northstar Member",
                email="member@northstar.com",
                invite_code=code,
            ),
            headers=csrf_headers(member_client),
        )
        assert joined.status_code == 202
        finish_signup(member_client, "member@northstar.com", otp_codes)

        db = database.SessionLocal()
        try:
            member_id = db.query(User.id).filter_by(email="member@northstar.com").scalar()
        finally:
            db.close()
        assert member_id

        changed = client.patch(
            f"/api/v1/auth/workspace/members/{member_id}",
            json={"role": "viewer"},
            headers=csrf_headers(client),
        )
        assert changed.status_code == 200
        assert changed.json()["role"] == "viewer"
        assert member_client.get("/api/v1/auth/me").status_code == 200

        removed = client.delete(
            f"/api/v1/auth/workspace/members/{member_id}",
            headers=csrf_headers(client),
        )
        assert removed.status_code == 204
        assert member_client.get("/api/v1/auth/me").status_code == 401


def test_member_cannot_manage_another_member(client, otp_codes):
    """A non-admin must receive 403 even for a member in the same tenant."""

    _owner_email, code = _create_owner_and_invite(client, otp_codes, role="viewer")
    with TestClient(client.app) as member_client:
        joined = member_client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email="viewer@northstar.com", invite_code=code),
            headers=csrf_headers(member_client),
        )
        assert joined.status_code == 202
        finish_signup(member_client, "viewer@northstar.com", otp_codes)

        db = database.SessionLocal()
        try:
            owner_id = db.query(User.id).filter_by(email="owner@northstar.com").scalar()
        finally:
            db.close()

        response = member_client.patch(
            f"/api/v1/auth/workspace/members/{owner_id}",
            json={"role": "editor"},
            headers=csrf_headers(member_client),
        )
        assert response.status_code == 403
