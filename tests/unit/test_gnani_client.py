"""Gnani STT transport tests without network access."""

from __future__ import annotations

import json
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


def test_transcribe_uses_gnani_multipart_contract():
    with patch("apps.core.gnani_client.urllib.request.urlopen", return_value=_Response()) as request_open:
        result = GnaniClient(api_key="secret", endpoint="https://stt.example").transcribe(
            b"OggS audio", "voice.ogg", language_code="auto"
        )
    request = request_open.call_args.args[0]
    body = request.data.decode("utf-8")
    assert request.headers["X-api-key-id"] == "secret"
    assert 'name="audio_file"; filename="voice.ogg"' in body
    assert 'name="language_code"' in body and "auto" in body
    assert 'name="preferred_language"' in body
    assert 'name="format"' in body and "transcribe" in body
    assert result.transcript == "नमस्ते"
    assert result.language_code == "hi-IN"


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
