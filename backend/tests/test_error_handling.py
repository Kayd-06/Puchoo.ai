"""Unexpected server errors are logged but never disclosed to API clients."""

from fastapi.testclient import TestClient


def test_unhandled_exception_returns_generic_message(app):
    @app.get("/_test/unhandled")
    def unhandled():
        raise RuntimeError("database failed at /private/app/db.py password=secret")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_test/unhandled")

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected error occurred."}
    assert "/private/app" not in response.text
    assert "password=secret" not in response.text
