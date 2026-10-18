"""Small, dependency-free Gnani Vachana speech client."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass


DEFAULT_ENDPOINT = "https://api.vachana.ai/stt/v3"
DEFAULT_TTS_ENDPOINT = "https://api.vachana.ai/api/v1/tts/inference"
DEFAULT_LANGUAGE_CODE = "en-IN"
MAX_TTS_TEXT_CHARS = 2000
SUPPORTED_LANGUAGE_CODES = frozenset({
    "bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN",
    "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN",
})


class GnaniConfigurationError(RuntimeError):
    """Raised without exposing upstream request details or credentials."""


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    language_code: str | None


class GnaniClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        tts_endpoint: str | None = None,
        timeout_seconds: int = 45,
    ) -> None:
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
        self.tts_endpoint = tts_endpoint or os.getenv("GNANI_TTS_ENDPOINT", DEFAULT_TTS_ENDPOINT)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _multipart(audio: bytes, filename: str, language_code: str) -> tuple[bytes, str]:
        boundary = f"----PuchooGnani{uuid.uuid4().hex}"
        fields = [("language_code", language_code), ("format", "transcribe")]
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
        selected_language = language_code or os.getenv("GNANI_STT_LANGUAGE", DEFAULT_LANGUAGE_CODE)
        selected_language = selected_language.strip() if isinstance(selected_language, str) and selected_language.strip() else DEFAULT_LANGUAGE_CODE
        if selected_language not in SUPPORTED_LANGUAGE_CODES:
            raise GnaniConfigurationError("GNANI_STT_LANGUAGE must be a supported Gnani BCP-47 language code.")
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

    def synthesize(self, text: str, *, language_code: str) -> bytes:
        """Return a short, selected-language Gnani Timbre WAV clip."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must not be empty")
        spoken_text = text.strip()
        if len(spoken_text) > MAX_TTS_TEXT_CHARS:
            raise ValueError(f"text must be at most {MAX_TTS_TEXT_CHARS} characters")
        selected_language = language_code.strip() if isinstance(language_code, str) else ""
        if selected_language not in SUPPORTED_LANGUAGE_CODES:
            raise GnaniConfigurationError("language_code must be a supported Gnani BCP-47 language code.")

        payload = {
            "text": spoken_text,
            "model": "timbre-v3.0",
            "voice": "Shivani",
            "language": selected_language,
            "audio_config": {
                "sample_rate": 24000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        request = urllib.request.Request(
            self.tts_endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "X-API-Key-ID": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/wav",
                "User-Agent": "PuchooAI/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get("Content-Type", "")
                audio = response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise GnaniConfigurationError("Gnani speech is temporarily unavailable.") from exc
        if not isinstance(content_type, str) or not content_type.lower().startswith("audio/wav"):
            raise GnaniConfigurationError("Gnani returned an invalid speech response.")
        if not audio or not audio.startswith(b"RIFF") or b"WAVE" not in audio[:16]:
            raise GnaniConfigurationError("Gnani returned an invalid speech response.")
        return audio
