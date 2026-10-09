"""Boundary checks for the optional Sarvam integration."""

from fastapi.testclient import TestClient
from uuid import uuid4

from apps.api.routers import sarvam
from backend.main import create_app
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload


def test_translation_provider_errors_are_not_returned_to_the_browser(monkeypatch, otp_codes):
    class FailingClient:
        def translate(self, *_args, **_kwargs):
            raise RuntimeError("provider failure at /internal/provider with token=do-not-return")

    monkeypatch.setattr(sarvam, "SarvamClient", FailingClient)
    with TestClient(create_app(include_product=True)) as client:
        email = f"owner-{uuid4().hex}@sarvamsecurity.com"
        assert client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email=email),
            headers=csrf_headers(client),
        ).status_code == 202
        finish_signup(client, email, otp_codes)

        response = client.post(
            "/api/sarvam/translate",
            json={"text": "translate this", "target_language": "hi-IN"},
            headers=csrf_headers(client),
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "Translation is temporarily unavailable."
    assert "internal/provider" not in response.text
    assert "do-not-return" not in response.text


def test_translation_schema_rejects_unknown_fields_and_oversized_text():
    unknown = sarvam.TranslationRequest.model_validate
    try:
        unknown({"text": "hello", "target_language": "hi-IN", "debug": True})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown fields must be rejected")

    try:
        unknown({"text": "x" * 2_001, "target_language": "hi-IN"})
    except ValueError:
        pass
    else:
        raise AssertionError("oversized translation input must be rejected")
