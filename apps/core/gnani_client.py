"""Small, dependency-free Gnani Vachana speech-to-text client."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass


DEFAULT_ENDPOINT = "https://api.vachana.ai/stt/v3"


class GnaniConfigurationError(RuntimeError):
    """Raised without exposing upstream request details or credentials."""


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    language_code: str | None


class GnaniClient:
    def __init__(self, *, api_key: str | None = None, endpoint: str | None = None, timeout_seconds: int = 45) -> None:
        if api_key is None:
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except ImportError:
                pass
        self.api_key = api_key or os.getenv("GNANI_API_KEY")
        if not self.api_key:
            raise GnaniConfigurationError("GNANI_API_KEY is not configured.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.endpoint = endpoint or os.getenv("GNANI_STT_ENDPOINT", DEFAULT_ENDPOINT)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _multipart(audio: bytes, filename: str, language_code: str) -> tuple[bytes, str]:
        boundary = f"----PuchooGnani{uuid.uuid4().hex}"
        fields = (("language_code", language_code), ("preferred_language", language_code), ("format", "transcribe"))
        chunks: list[bytes] = []
        for key, value in fields:
            chunks.extend((f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(), value.encode(), b"\r\n"))
        safe_name = os.path.basename(filename) or "audio.webm"
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="audio_file"; filename="{safe_name}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            audio,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ))
        return b"".join(chunks), boundary

    def transcribe(self, audio: bytes, filename: str, *, language_code: str | None = None) -> TranscriptionResult:
        if not audio:
            raise ValueError("audio must not be empty")
        selected_language = language_code or os.getenv("GNANI_STT_LANGUAGE", "auto")
        selected_language = selected_language.strip() if isinstance(selected_language, str) and selected_language.strip() else "auto"
        body, boundary = self._multipart(audio, filename, selected_language)
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "X-API-Key-ID": self.api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
                "User-Agent": "PuchooAI/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise GnaniConfigurationError("Gnani transcription is temporarily unavailable.") from exc
        transcript = parsed.get("transcript") if isinstance(parsed, dict) else None
        if not isinstance(transcript, str) or not transcript.strip():
            raise GnaniConfigurationError("Gnani returned an invalid transcription response.")
        language = parsed.get("language_code") or parsed.get("language")
        normalized = language.strip() if isinstance(language, str) and re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", language.strip()) else None
        return TranscriptionResult(transcript.strip(), normalized)
