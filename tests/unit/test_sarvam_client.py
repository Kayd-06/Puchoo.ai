"""Sarvam adapter tests using a fake client and no API calls."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from apps.core.sarvam_client import SarvamClient


class _SpeechToText:
    def transcribe(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(transcript="नमस्ते", language_code="hi-IN")


class _Text:
    def translate(self, **kwargs: object) -> dict[str, str]:
        self.translate_kwargs = kwargs
        return {"translated_text": "नमस्ते"}

    def transliterate(self, **kwargs: object) -> dict[str, str]:
        self.transliterate_kwargs = kwargs
        return {"transliterated_text": "namaste"}


class _BatchText(_Text):
    def translate(self, **kwargs: object) -> dict[str, str]:
        self.translate_kwargs = kwargs
        return {"translated_text": kwargs["input"].replace("Women", "महिला").replace("Men", "पुरुष")}


class _Client:
    def __init__(self) -> None:
        self.speech_to_text = _SpeechToText()
        self.text = _Text()


class _BatchClient(_Client):
    def __init__(self) -> None:
        self.speech_to_text = _SpeechToText()
        self.text = _BatchText()


class SarvamClientTests(unittest.TestCase):
    def test_transcribes_audio_through_saaras(self) -> None:
        fake = _Client()
        client = SarvamClient(client=fake)
        self.assertEqual("नमस्ते", client.transcribe(b"audio", "voice.wav"))
        self.assertEqual("transcribe", fake.speech_to_text.kwargs["mode"])
        self.assertEqual("unknown", fake.speech_to_text.kwargs["language_code"])

    def test_voice_translation_auto_detects_language(self) -> None:
        fake = _Client()
        client = SarvamClient(client=fake)
        self.assertEqual("नमस्ते", client.transcribe(b"audio", "voice.webm", translate_to_english=True))
        self.assertEqual("translate", fake.speech_to_text.kwargs["mode"])
        self.assertEqual("unknown", fake.speech_to_text.kwargs["language_code"])

    def test_transcription_returns_the_detected_language(self) -> None:
        result = SarvamClient(client=_Client()).transcribe_with_metadata(b"audio", "voice.webm")
        self.assertEqual("नमस्ते", result.transcript)
        self.assertEqual("hi-IN", result.language_code)

    def test_translates_table_values_in_a_single_mapped_batch(self) -> None:
        translated = SarvamClient(client=_BatchClient()).translate_many(["Women Item 795", "Men Item 222"], "hi-IN")
        self.assertEqual("महिला Item 795", translated["Women Item 795"])
        self.assertEqual("पुरुष Item 222", translated["Men Item 222"])

    def test_translates_and_transliterates_text(self) -> None:
        client = SarvamClient(client=_Client())
        self.assertEqual("नमस्ते", client.translate("Hello", "hi-IN"))
        self.assertEqual("namaste", client.transliterate("नमस्ते", "en-IN", source_language="hi-IN"))
