"""Sarvam adapter tests using a fake client and no API calls."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from apps.core.sarvam_client import SarvamClient


class _SpeechToText:
    def transcribe(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(transcript="नमस्ते")


class _Text:
    def translate(self, **kwargs: object) -> dict[str, str]:
        self.translate_kwargs = kwargs
        return {"translated_text": "नमस्ते"}

    def transliterate(self, **kwargs: object) -> dict[str, str]:
        self.transliterate_kwargs = kwargs
        return {"transliterated_text": "namaste"}


class _Client:
    def __init__(self) -> None:
        self.speech_to_text = _SpeechToText()
        self.text = _Text()


class SarvamClientTests(unittest.TestCase):
    def test_transcribes_audio_through_saaras(self) -> None:
        fake = _Client()
        client = SarvamClient(client=fake)
        self.assertEqual("नमस्ते", client.transcribe(b"audio", "voice.wav"))
        self.assertEqual("transcribe", fake.speech_to_text.kwargs["mode"])

    def test_translates_and_transliterates_text(self) -> None:
        client = SarvamClient(client=_Client())
        self.assertEqual("नमस्ते", client.translate("Hello", "hi-IN"))
        self.assertEqual("namaste", client.transliterate("नमस्ते", "en-IN", source_language="hi-IN"))
