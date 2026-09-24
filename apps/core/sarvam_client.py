"""Optional Sarvam adapters for Indian-language voice and regional output."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
import re
from typing import Any


DEFAULT_STT_MODEL = "saaras:v3"
DEFAULT_TRANSLATION_MODEL = "sarvam-translate:v1"


class SarvamConfigurationError(RuntimeError):
    """Raised when an optional Sarvam feature has not been configured yet."""


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    language_code: str | None


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

    def transcribe(self, audio: bytes, filename: str = "question.wav", *, translate_to_english: bool = False) -> str:
        """Transcribe audio, optionally auto-detecting and translating speech to English."""

        return self.transcribe_with_metadata(
            audio,
            filename,
            translate_to_english=translate_to_english,
        ).transcript

    def transcribe_with_metadata(
        self, audio: bytes, filename: str = "question.wav", *, translate_to_english: bool = False
    ) -> TranscriptionResult:
        """Return the transcript together with Sarvam's detected BCP-47 language code."""

        if not audio:
            raise ValueError("Audio is empty.")
        stream = BytesIO(audio)
        stream.name = filename
        options: dict[str, Any] = {
            "file": stream,
            "model": self.stt_model,
            "mode": "translate" if translate_to_english else "transcribe",
            "language_code": "unknown",
        }
        response = self._client.speech_to_text.transcribe(**options)
        language_code = response.get("language_code") if isinstance(response, dict) else getattr(response, "language_code", None)
        return TranscriptionResult(
            transcript=_value(response, "transcript"),
            language_code=language_code if isinstance(language_code, str) and language_code.strip() else None,
        )

    def translate(self, text: str, target_language: str, *, source_language: str = "en-IN") -> str:
        if not text.strip():
            raise ValueError("Text is required for translation.")
        response = self._client.text.translate(
            input=text[:2000], source_language_code=source_language, target_language_code=target_language,
            model=self.translation_model,
        )
        return _value(response, "translated_text")

    def translate_many(self, texts: list[str], target_language: str, *, source_language: str = "en-IN") -> dict[str, str]:
        """Translate short UI/data labels in bounded batches while retaining a stable mapping."""

        unique_texts = list(dict.fromkeys(text for text in texts if text.strip()))
        translated: dict[str, str] = {}
        batch: list[tuple[int, str]] = []
        batch_size = 0

        def flush() -> None:
            nonlocal batch, batch_size
            if not batch:
                return
            payload = "\n".join(f"[[PCH{index:04d}]] {text}" for index, text in batch)
            response = self.translate(payload, target_language, source_language=source_language)
            matches = list(re.finditer(r"\[\[PCH(\d{4})\]\]", response))
            by_index = {index: text for index, text in batch}
            for match_index, match in enumerate(matches):
                source_index = int(match.group(1))
                next_start = matches[match_index + 1].start() if match_index + 1 < len(matches) else len(response)
                value = response[match.end():next_start].strip()
                if source_index in by_index and value:
                    translated[by_index[source_index]] = value
            batch = []
            batch_size = 0

        for index, text in enumerate(unique_texts):
            entry_size = len(text) + 16
            if batch and batch_size + entry_size > 1_700:
                flush()
            batch.append((index, text))
            batch_size += entry_size
        flush()
        return translated

    def transliterate(self, text: str, target_language: str, *, source_language: str = "en-IN") -> str:
        if not text.strip():
            raise ValueError("Text is required for transliteration.")
        response = self._client.text.transliterate(
            input=text[:1000], source_language_code=source_language, target_language_code=target_language,
        )
        return _value(response, "transliterated_text")
