"""Regression coverage for authenticated, tenant-scoped notifications."""

from fastapi.testclient import TestClient

from backend import database
from backend.main import create_app
from backend.models import User
from backend.notifications import create_notification
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload


def test_notifications_are_private_and_can_be_marked_read(app, otp_codes):
    """Only the signed-in account can fetch or change its notifications."""

    with TestClient(create_app(include_product=True)) as client:
        email = "ada@college.edu"
        signup = client.post("/api/v1/auth/signup", json=signup_payload(email=email), headers=csrf_headers(client))
        assert signup.status_code == 202
        finish_signup(client, email, otp_codes)

        db = database.SessionLocal()
        try:
            user = db.query(User).filter_by(email=email).one()
            other = User(
                full_name="Grace Hopper",
                email="grace@college.edu",
                password_hash="not-used-in-this-test",
                workspace_type="personal",
            )
            db.add(other)
            db.flush()
            own = create_notification(
                db,
                user_id=user.id,
                kind="query_completed",
                title="Your query is ready",
                body="A real event for Ada.",
            )
            other_event = create_notification(
                db,
                user_id=other.id,
                kind="query_completed",
                title="Private to Grace",
            )
            db.commit()
            own_id = own.id
            other_id = other_event.id
        finally:
            db.close()

        listed = client.get("/api/notifications/")
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["unread_count"] == 1
        assert [item["id"] for item in payload["items"]] == [own_id]

        forbidden = client.post(f"/api/notifications/{other_id}/read", headers=csrf_headers(client))
        assert forbidden.status_code == 404

        marked = client.post(f"/api/notifications/{own_id}/read", headers=csrf_headers(client))
        assert marked.status_code == 200
        assert client.get("/api/notifications/").json()["unread_count"] == 0
