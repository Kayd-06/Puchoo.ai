"""Optional Sarvam adapters for Indian-language voice and regional output."""

from __future__ import annotations

from io import BytesIO
import os
from typing import Any


DEFAULT_STT_MODEL = "saaras:v3"
DEFAULT_TRANSLATION_MODEL = "sarvam-translate:v1"


class SarvamConfigurationError(RuntimeError):
    """Raised when an optional Sarvam feature has not been configured yet."""


def _value(response: Any, field: str) -> str:
    value = response.get(field) if isinstance(response, dict) else getattr(response, field, None)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("Sarvam returned no usable text.")
    return value.strip()


class SarvamClient:
    """Small adapter over the official SDK; imports it only when feature is used."""

    def __init__(self, *, api_key: str | None = None, client: Any | None = None) -> None:
        if client is None:
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass
        key = api_key or os.getenv("SARVAM_API_KEY")
        self.stt_model = os.getenv("SARVAM_STT_MODEL", DEFAULT_STT_MODEL)
        self.translation_model = os.getenv("SARVAM_TRANSLATION_MODEL", DEFAULT_TRANSLATION_MODEL)
        if client is not None:
            self._client = client
            return
        if not key:
            raise SarvamConfigurationError("SARVAM_API_KEY is not configured. Add it to your local .env when ready.")
        try:
            from sarvamai import SarvamAI
        except ImportError as exc:
            raise SarvamConfigurationError("The Sarvam SDK is not installed. Install dependencies with `pip install -r requirements.txt`.") from exc
        self._client = SarvamAI(api_subscription_key=key)

    def transcribe(self, audio: bytes, filename: str = "question.wav") -> str:
        if not audio:
            raise ValueError("Audio is empty.")
        stream = BytesIO(audio)
        stream.name = filename
        response = self._client.speech_to_text.transcribe(file=stream, model=self.stt_model, mode="transcribe")
        return _value(response, "transcript")

    def translate(self, text: str, target_language: str, *, source_language: str = "en-IN") -> str:
        if not text.strip():
            raise ValueError("Text is required for translation.")
        response = self._client.text.translate(
            input=text[:2000], source_language_code=source_language, target_language_code=target_language,
            model=self.translation_model,
        )
        return _value(response, "translated_text")

    def transliterate(self, text: str, target_language: str, *, source_language: str = "en-IN") -> str:
        if not text.strip():
            raise ValueError("Text is required for transliteration.")
        response = self._client.text.transliterate(
            input=text[:1000], source_language_code=source_language, target_language_code=target_language,
        )
        return _value(response, "transliterated_text")
