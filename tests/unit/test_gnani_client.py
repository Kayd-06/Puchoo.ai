"""Gnani STT transport tests without network access."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from apps.core.gnani_client import GnaniClient, GnaniConfigurationError


class _Response:
    def read(self) -> bytes:
        return json.dumps({"transcript": "नमस्ते", "language_code": "hi-IN"}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _AudioResponse:
    headers = {"Content-Type": "audio/wav"}

    def __init__(self, audio: bytes = b"RIFF....WAVEfmt ") -> None:
        self.audio = audio

    def read(self) -> bytes:
        return self.audio

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_transcribe_uses_gnani_multipart_contract_with_a_supported_default_language(monkeypatch):
    monkeypatch.delenv("GNANI_STT_LANGUAGE", raising=False)
    with patch("apps.core.gnani_client.urllib.request.urlopen", return_value=_Response()) as request_open:
        result = GnaniClient(api_key="secret", endpoint="https://stt.example").transcribe(
            b"OggS audio", "voice.ogg"
        )
    request = request_open.call_args.args[0]
    body = request.data.decode("utf-8")
    assert request.headers["X-api-key-id"] == "secret"
    assert 'name="audio_file"; filename="voice.ogg"' in body
    assert 'name="language_code"' in body and "en-IN" in body
    assert 'name="preferred_language"' not in body
    assert 'name="format"' in body and "transcribe" in body
    assert result.transcript == "नमस्ते"
    assert result.language_code == "hi-IN"


def test_transcribe_does_not_send_undocumented_preferred_language_field():
    with patch("apps.core.gnani_client.urllib.request.urlopen", return_value=_Response()) as request_open:
        GnaniClient(api_key="secret", endpoint="https://stt.example").transcribe(
            b"OggS audio", "voice.ogg", language_code="hi-IN"
        )
    body = request_open.call_args.args[0].data.decode("utf-8")
    assert 'name="preferred_language"' not in body
    assert "hi-IN" in body


def test_transcribe_rejects_auto_language_for_the_rest_endpoint():
    with pytest.raises(GnaniConfigurationError, match="supported Gnani BCP-47"):
        GnaniClient(api_key="secret").transcribe(b"OggS audio", "voice.ogg", language_code="auto")


def test_missing_key_and_invalid_response_are_safe(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "")
    with pytest.raises(GnaniConfigurationError):
        GnaniClient()

    class _BlankResponse(_Response):
        def read(self) -> bytes:
            return b'{"transcript":""}'

    with patch("apps.core.gnani_client.urllib.request.urlopen", return_value=_BlankResponse()):
        with pytest.raises(GnaniConfigurationError, match="invalid transcription"):
            GnaniClient(api_key="secret").transcribe(b"audio", "voice.webm")


def test_synthesize_uses_gnani_timbre_contract_and_returns_wav_bytes():
    with patch("apps.core.gnani_client.urllib.request.urlopen", return_value=_AudioResponse()) as request_open:
        audio = GnaniClient(api_key="secret").synthesize("नमस्ते", language_code="hi-IN")

    request = request_open.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://api.vachana.ai/api/v1/tts/inference"
    assert request.headers["X-api-key-id"] == "secret"
    assert request.headers["Content-type"] == "application/json"
    assert request.headers["Accept"] == "audio/wav"
    assert payload == {
        "text": "नमस्ते",
        "model": "timbre-v3.0",
        "voice": "Shivani",
        "language": "hi-IN",
        "audio_config": {
            "sample_rate": 24000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    assert audio.startswith(b"RIFF")


@pytest.mark.parametrize(
    ("text", "language_code", "message"),
    [
        ("", "en-IN", "text must not be empty"),
        ("x" * 2001, "en-IN", "at most 2000"),
        ("Hello", "auto", "supported Gnani BCP-47"),
    ],
)
def test_synthesize_rejects_invalid_text_or_language(text, language_code, message):
    with pytest.raises((GnaniConfigurationError, ValueError), match=message):
        GnaniClient(api_key="secret").synthesize(text, language_code=language_code)


def test_synthesize_rejects_non_audio_or_empty_upstream_responses():
    class _JsonResponse(_AudioResponse):
        headers = {"Content-Type": "application/json"}

    with patch("apps.core.gnani_client.urllib.request.urlopen", return_value=_JsonResponse()):
        with pytest.raises(GnaniConfigurationError, match="invalid speech response"):
            GnaniClient(api_key="secret").synthesize("Hello", language_code="en-IN")

    with patch("apps.core.gnani_client.urllib.request.urlopen", return_value=_AudioResponse(b"")):
        with pytest.raises(GnaniConfigurationError, match="invalid speech response"):
            GnaniClient(api_key="secret").synthesize("Hello", language_code="en-IN")


def test_synthesize_maps_upstream_errors_to_a_safe_message():
    upstream_error = urllib.error.HTTPError(
        "https://api.vachana.ai/api/v1/tts/inference", 403, "Forbidden", {}, None
    )
    with patch("apps.core.gnani_client.urllib.request.urlopen", side_effect=upstream_error):
        with pytest.raises(GnaniConfigurationError, match="speech is temporarily unavailable"):
            GnaniClient(api_key="secret").synthesize("Hello", language_code="en-IN")
