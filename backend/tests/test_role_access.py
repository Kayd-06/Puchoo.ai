"""Role boundaries must be enforced by API routes, not only hidden in the UI."""

from fastapi.testclient import TestClient

from apps.api.session import session_manager
from backend import database
from backend.main import create_app
from backend.models import User
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload


def test_viewer_cannot_prompt_upload_connect_or_change_workspace(client, otp_codes):
    """A viewer code permits only tenant-scoped reading of existing history."""

    owner_email = "owner@business.com"
    owner_signup = client.post(
        "/api/v1/auth/signup",
        json=signup_payload(
            full_name="Workspace Owner",
            email=owner_email,
            workspace_type="business",
            workspace_name="Northstar",
        ),
        headers=csrf_headers(client),
    )
    assert owner_signup.status_code == 202
    finish_signup(client, owner_email, otp_codes)
    invite = client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "viewer"},
        headers=csrf_headers(client),
    )
    assert invite.status_code == 200

    db = database.SessionLocal()
    try:
        owner_id = db.query(User).filter_by(email=owner_email).one().id
    finally:
        db.close()

    workspace_id = "viewer-permissions-workspace"
    session_manager.workspaces[workspace_id] = {
        "id": workspace_id,
        "name": "Northstar reporting",
        "owner_user_id": owner_id,
        "database_uri": "sqlite:///:memory:",
        "dialect": "sqlite",
    }
    session_manager.workspace_guardrails[workspace_id] = session_manager.DEFAULT_GUARDRAILS.copy()
    session_manager.query_history[workspace_id] = []

    try:
        with TestClient(create_app(include_product=True)) as viewer_client:
            viewer_email = "viewer@personal.com"
            joined = viewer_client.post(
                "/api/v1/auth/signup",
                json=signup_payload(
                    full_name="Read Only Viewer",
                    email=viewer_email,
                    workspace_type="personal",
                    invite_code=invite.json()["code"],
                ),
                headers=csrf_headers(viewer_client),
            )
            assert joined.status_code == 202
            finish_signup(viewer_client, viewer_email, otp_codes)

            assert viewer_client.get(f"/api/history/{workspace_id}").status_code == 200
            assert viewer_client.get(f"/api/workspaces/{workspace_id}").status_code == 403
            assert viewer_client.get(f"/api/workspaces/{workspace_id}/schema").status_code == 403
            assert viewer_client.post(
                f"/api/query/{workspace_id}/generate",
                json={"question": "Show revenue"},
                headers=csrf_headers(viewer_client),
            ).status_code == 403
            assert viewer_client.post(
                "/api/workspaces/upload",
                files={"file": ("report.csv", b"month,total\nJan,4\n", "text/csv")},
                headers=csrf_headers(viewer_client),
            ).status_code == 403
            assert viewer_client.post(
                "/api/workspaces/server",
                json={"name": "Hidden", "engine": "postgresql", "host": "db.test", "port": 5432, "database": "app", "username": "readonly", "password": "secret"},
                headers=csrf_headers(viewer_client),
            ).status_code == 403
            assert viewer_client.post(
                "/api/sarvam/translate",
                json={"text": "show the report"},
                headers=csrf_headers(viewer_client),
            ).status_code == 403
            assert viewer_client.put(
                f"/api/settings/guardrails/{workspace_id}",
                json={"max_rows": 100, "timeout_seconds": 10, "confirm_complex_queries": True},
                headers=csrf_headers(viewer_client),
            ).status_code == 403
            assert viewer_client.delete(
                f"/api/history/{workspace_id}",
                headers=csrf_headers(viewer_client),
            ).status_code == 403
    finally:
        session_manager.workspaces.pop(workspace_id, None)
        session_manager.workspace_guardrails.pop(workspace_id, None)
        session_manager.query_history.pop(workspace_id, None)
        session_manager.active_proposals.pop(workspace_id, None)
        session_manager.schema_snapshots.pop(f"schema_{workspace_id}", None)


def test_admin_issued_code_stays_in_the_original_tenant(client, otp_codes):
    """An admin can invite colleagues without accidentally creating a new tenant."""

    owner_email = "owner@academy.com"
    assert client.post(
        "/api/v1/auth/signup",
        json=signup_payload(
            full_name="Institution Owner",
            email=owner_email,
            workspace_type="institution",
            workspace_name="North Campus",
        ),
        headers=csrf_headers(client),
    ).status_code == 202
    finish_signup(client, owner_email, otp_codes)
    admin_code = client.post(
        "/api/v1/auth/workspace/invite",
        json={"role": "admin"},
        headers=csrf_headers(client),
    ).json()["code"]

    with TestClient(create_app(include_product=False)) as admin_client:
        admin_email = "admin@academy.com"
        assert admin_client.post(
            "/api/v1/auth/signup",
            json=signup_payload(
                full_name="Campus Admin",
                email=admin_email,
                workspace_type="personal",
                invite_code=admin_code,
            ),
            headers=csrf_headers(admin_client),
        ).status_code == 202
        finish_signup(admin_client, admin_email, otp_codes)
        viewer_code = admin_client.post(
            "/api/v1/auth/workspace/invite",
            json={"role": "viewer"},
            headers=csrf_headers(admin_client),
        )
        assert viewer_code.status_code == 200

    with TestClient(create_app(include_product=False)) as viewer_client:
        viewer_email = "viewer@academy.com"
        assert viewer_client.post(
            "/api/v1/auth/signup",
            json=signup_payload(
                full_name="Campus Viewer",
                email=viewer_email,
                workspace_type="business",
                invite_code=viewer_code.json()["code"],
            ),
            headers=csrf_headers(viewer_client),
        ).status_code == 202

    db = database.SessionLocal()
    try:
        owner = db.query(User).filter_by(email=owner_email).one()
        viewer = db.query(User).filter_by(email="viewer@academy.com").one()
        assert viewer.workspace_owner_id == owner.id
        assert viewer.workspace_role == "viewer"
        assert viewer.workspace_type == "institution"
    finally:
        db.close()
