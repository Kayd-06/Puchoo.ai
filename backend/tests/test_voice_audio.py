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
        assert (await voice._read_audio(file))[0] == content

        file = UploadFile(filename="voice.mp4", file=BytesIO(content))
        assert (await voice._read_audio(file))[0] == content

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
        assert client.calls == [(content, "audio.ogg", "hi-IN")]

    asyncio.run(check())


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("voice.webm", b"\x1a\x45\xdf\xa3webm"),
        ("voice.mp3", b"ID3mp3"),
        ("voice.flac", b"fLaC"),
        ("voice", b"OggS voice"),
    ],
)
def test_unsupported_audio_formats_are_rejected_before_gnani(filename, content):
    async def check() -> None:
        with pytest.raises(HTTPException) as exc:
            await voice._read_audio(UploadFile(filename=filename, file=BytesIO(content)))
        assert exc.value.status_code == 400
        assert "OGG, M4A, MP4, or WAV" in exc.value.detail

    asyncio.run(check())


def test_transcription_never_forwards_the_client_filename(monkeypatch):
    class FakeGnaniClient:
        def __init__(self):
            self.calls = []

        def transcribe(self, audio, filename, *, language_code):
            self.calls.append((filename, language_code))
            return TranscriptionResult("hello", None)

    client = FakeGnaniClient()
    monkeypatch.setattr(voice, "GnaniClient", lambda: client)

    async def check() -> None:
        file = UploadFile(filename='x"\r\nX-Evil: 1.wav', file=BytesIO(b"RIFF\x00\x00\x00\x00WAVEfmt "))
        response = await voice.transcribe(file, language_code=None, user={})
        assert response == {"transcript": "hello", "language_code": None}
        assert client.calls == [("audio.wav", None)]

    asyncio.run(check())


def test_transcription_runs_off_the_event_loop(monkeypatch):
    """A slow Gnani call must not block every other request on the server."""
    class FakeGnaniClient:
        def transcribe(self, audio, filename, *, language_code):
            return TranscriptionResult("hello", "en-IN")

    fake = FakeGnaniClient()
    monkeypatch.setattr(voice, "GnaniClient", lambda: fake)
    threadpool_calls = []

    async def fake_run_in_threadpool(function, *args, **kwargs):
        threadpool_calls.append((function, args, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(voice, "run_in_threadpool", fake_run_in_threadpool)

    async def check() -> None:
        file = UploadFile(filename="voice.ogg", file=BytesIO(b"OggS voice"))
        await voice.transcribe(file, language_code="en-IN", user={})

    asyncio.run(check())
    assert threadpool_calls == [(fake.transcribe, (b"OggS voice", "audio.ogg"), {"language_code": "en-IN"})]


def test_transcription_rejects_unsupported_language():
    async def check() -> None:
        file = UploadFile(filename="voice.ogg", file=BytesIO(b"OggS voice"))
        with pytest.raises(HTTPException) as exc:
            await voice.transcribe(file, language_code="auto", user={})
        assert exc.value.status_code == 400

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
