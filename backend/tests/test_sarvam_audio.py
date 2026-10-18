"""Tests for audio file parsing and validation."""

import asyncio
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from apps.api.routers import voice
from apps.core.gnani_client import GnaniConfigurationError, TranscriptionResult
from backend.main import create_app
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload

def test_mp4_m4a_audio_uploads():
    """ISO-BMFF audio files from Safari are accepted using their ftyp signature."""
    async def check() -> None:
        # Valid MP4 has the ISO-BMFF `ftyp` marker at byte four.
        content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"
        file = UploadFile(filename="voice.m4a", file=BytesIO(content))
        assert await voice._read_audio(file) == content

        file = UploadFile(filename="voice.mp4", file=BytesIO(content))
        assert await voice._read_audio(file) == content

        invalid_content = b"RIFF\x00\x00\x00\x00WAVE"
        file = UploadFile(filename="voice.m4a", file=BytesIO(invalid_content))
        with pytest.raises(HTTPException) as exc:
            await voice._read_audio(file)
        assert exc.value.status_code == 400
        assert "does not match its declared format" in exc.value.detail

    asyncio.run(check())


def test_voice_transcription_passes_the_selected_gnani_language(monkeypatch):
    """The selected language must reach Gnani unchanged, not fall back to English."""
    class FakeGnaniClient:
        def __init__(self):
            self.calls = []

        def transcribe(self, audio, filename, *, language_code):
            self.calls.append((audio, filename, language_code))
            return TranscriptionResult("मेरे खर्चे बताओ", language_code)

    client = FakeGnaniClient()
    monkeypatch.setattr(voice, "GnaniClient", lambda: client)

    async def check() -> None:
        content = b"OggS voice"
        file = UploadFile(filename="voice.ogg", file=BytesIO(content))
        response = await voice.transcribe(file, language_code="hi-IN", user={})
        assert response == {"transcript": "मेरे खर्चे बताओ", "language_code": "hi-IN"}
        assert client.calls == [(content, "voice.ogg", "hi-IN")]

    asyncio.run(check())


def test_synthesis_requires_a_signed_in_workspace_user(monkeypatch):
    monkeypatch.setattr(voice, "GnaniClient", lambda: None)
    with TestClient(create_app(include_product=True)) as client:
        response = client.post(
            "/api/voice/synthesize",
            json={"text": "Your expenses are 200.", "language_code": "en-IN"},
            headers=csrf_headers(client),
        )

    assert response.status_code == 401


def test_synthesis_returns_uncached_wav_for_an_authorized_language(monkeypatch, otp_codes):
    class FakeGnaniClient:
        def __init__(self):
            self.calls = []

        def synthesize(self, text, *, language_code):
            self.calls.append((text, language_code))
            return b"RIFF....WAVEfmt "

    fake = FakeGnaniClient()
    monkeypatch.setattr(voice, "GnaniClient", lambda: fake)
    threadpool_calls = []

    async def fake_run_in_threadpool(function, *args, **kwargs):
        threadpool_calls.append((function, args, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(voice, "run_in_threadpool", fake_run_in_threadpool)
    with TestClient(create_app(include_product=True)) as client:
        email = f"voice-{uuid4().hex}@example.com"
        assert client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email=email),
            headers=csrf_headers(client),
        ).status_code == 202
        finish_signup(client, email, otp_codes)

        response = client.post(
            "/api/voice/synthesize",
            json={"text": "आपका खर्च 200 है।", "language_code": "hi-IN"},
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b"RIFF....WAVEfmt "
    assert fake.calls == [("आपका खर्च 200 है।", "hi-IN")]
    assert threadpool_calls == [(fake.synthesize, ("आपका खर्च 200 है।",), {"language_code": "hi-IN"})]


def test_synthesis_rejects_invalid_requests_and_hides_provider_errors(monkeypatch, otp_codes):
    class FailingGnaniClient:
        def synthesize(self, *_args, **_kwargs):
            raise GnaniConfigurationError("provider returned token=do-not-return")

    monkeypatch.setattr(voice, "GnaniClient", FailingGnaniClient)
    with TestClient(create_app(include_product=True)) as client:
        email = f"voice-{uuid4().hex}@example.com"
        assert client.post(
            "/api/v1/auth/signup",
            json=signup_payload(email=email),
            headers=csrf_headers(client),
        ).status_code == 202
        finish_signup(client, email, otp_codes)

        invalid = client.post(
            "/api/voice/synthesize",
            json={"text": "Hello", "language_code": "auto"},
            headers=csrf_headers(client),
        )
        upstream = client.post(
            "/api/voice/synthesize",
            json={"text": "Hello", "language_code": "en-IN"},
            headers=csrf_headers(client),
        )

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Choose a supported speech language."
    assert upstream.status_code == 502
    assert upstream.json()["detail"] == "Speech synthesis is temporarily unavailable."
    assert "do-not-return" not in upstream.text
