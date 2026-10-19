"""Gnani gives the spoken language; Sarvam translates question and answer."""

import pytest

from apps.api.routers import query as query_router
from apps.core.gnani_client import SUPPORTED_LANGUAGE_CODES


class FakeSarvam:
    calls: list[tuple] = []

    def translate(self, text, target_language, *, source_language="en-IN"):
        FakeSarvam.calls.append(("translate", text, target_language, source_language))
        return f"[{target_language}] {text}"

    def translate_many(self, texts, target_language, *, source_language="en-IN"):
        FakeSarvam.calls.append(("translate_many", tuple(texts), target_language, source_language))
        return {text: f"[{target_language}] {text}" for text in texts}


@pytest.fixture
def fake_sarvam(monkeypatch):
    FakeSarvam.calls = []
    monkeypatch.setattr(query_router, "SarvamClient", FakeSarvam)
    monkeypatch.setattr(query_router, "_translation_cache", {})
    return FakeSarvam


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ta-IN", "ta-IN"),
        ("hi-IN", "hi-IN"),
        (" te-IN ", "te-IN"),
        ("hi", "hi-IN"),
        ("HI-in", "hi-IN"),
        ("ta_IN", "ta-IN"),
        ("hi-en", "hi-IN"),
        ("or-IN", "od-IN"),
        ("od-IN", "od-IN"),
        ("en-IN", None),
        ("en-US", None),
        ("en", None),
        ("auto", None),
        ("", None),
        (None, None),
        ("hi-IN-x", None),
    ],
)
def test_language_codes_are_mapped_to_sarvam_format(code, expected):
    assert query_router.to_sarvam_language(code) == expected


@pytest.mark.parametrize("code", sorted(SUPPORTED_LANGUAGE_CODES - {"en-IN"}))
def test_every_gnani_language_passes_through_unchanged(code):
    assert query_router.to_sarvam_language(code) == code


def test_question_is_translated_to_english_from_the_gnani_language(fake_sarvam):
    language = query_router._spoken_language("ta-IN")
    english = query_router._translate_for_sql("என் செலவுகள்", language)
    assert english == "[en-IN] என் செலவுகள்"
    assert fake_sarvam.calls == [("translate", "என் செலவுகள்", "en-IN", "ta-IN")]


def test_english_question_is_not_sent_to_sarvam(fake_sarvam):
    language = query_router._spoken_language("en-IN")
    assert query_router._translate_for_sql("total sales", language) == "total sales"
    assert fake_sarvam.calls == []


def test_answer_is_translated_back_to_the_spoken_language(fake_sarvam):
    language = query_router._spoken_language("ta-IN")
    assert query_router._translate_for_display("Total is 200.", language) == "[ta-IN] Total is 200."
    rows = query_router._localize_rows([{"area": "North", "total": 200}], language)
    assert rows == [{"area": "[ta-IN] North", "total": 200}]
    assert ("translate", "Total is 200.", "ta-IN", "en-IN") in fake_sarvam.calls
    assert ("translate_many", ("North",), "ta-IN", "en-IN") in fake_sarvam.calls


def test_translation_failure_blocks_the_question_but_not_the_answer(monkeypatch):
    class BrokenSarvam:
        def translate(self, *_args, **_kwargs):
            raise RuntimeError("down")

    monkeypatch.setattr(query_router, "SarvamClient", BrokenSarvam)
    monkeypatch.setattr(query_router, "_translation_cache", {})
    with pytest.raises(ValueError):
        query_router._translate_for_sql("मेरे खर्चे", "hi-IN")
    assert query_router._translate_for_display("Total is 200.", "hi-IN") == "Total is 200."
