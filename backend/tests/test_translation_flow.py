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


@pytest.mark.parametrize('question,language', [('पिछले महीने का खर्च बताओ', 'hi-IN'), ('Show total expenses', None)])
def test_typed_question_language_is_detected(question, language):
    assert query_router._infer_indic_language(question) == language


def test_hindi_question_answer_and_cells_keep_hindi(fake_sarvam):
    language = query_router._infer_indic_language('पिछले महीने का खर्च बताओ')
    assert query_router._translate_for_sql('पिछले महीने का खर्च बताओ', language).startswith('[en-IN]')
    assert query_router._translate_for_display('Total expenses', language).startswith('[hi-IN]')
    assert query_router._localize_rows([{'status': 'Paid', 'amount': 0}], language) == [{'status': '[hi-IN] Paid', 'amount': 0}]


def test_translation_outage_falls_back_to_english_and_records_failure(monkeypatch):
    class BrokenSarvam:
        def translate(self, *_args, **_kwargs):
            raise RuntimeError('down')
        def translate_many(self, *_args, **_kwargs):
            raise RuntimeError('down')
    monkeypatch.setattr(query_router, 'SarvamClient', BrokenSarvam)
    monkeypatch.setattr(query_router, '_translation_cache', {})
    failures = []
    assert query_router._translate_for_display('Total expenses', 'hi-IN', failures=failures) == 'Total expenses'
    assert query_router._localize_rows([{'status': 'Paid', 'amount': 3}], 'hi-IN', failures=failures) == [{'status': 'Paid', 'amount': 3}]
    assert failures == ['Total expenses', 'Paid']


def test_missing_row_translations_are_retried_in_one_batch(monkeypatch):
    calls = []
    class PartialSarvam:
        def translate(self, *_args, **_kwargs):
            raise AssertionError('per-value translate must not be used for rows')
        def translate_many(self, texts, language, **_kwargs):
            calls.append(list(texts))
            if len(calls) == 1:
                return {texts[0]: f'[{language}] {texts[0]}'}
            return {text: f'[{language}] {text}' for text in texts}
    monkeypatch.setattr(query_router, 'SarvamClient', PartialSarvam)
    rows = [{'status': 'Paid'}, {'status': 'Due'}, {'status': 'Late'}, {'status': 'Paid'}]
    failures = []
    result = query_router._localize_rows(rows, 'hi-IN', failures=failures)
    assert calls == [['Paid', 'Due', 'Late'], ['Due', 'Late']]
    assert [row['status'] for row in result] == ['[hi-IN] Paid', '[hi-IN] Due', '[hi-IN] Late', '[hi-IN] Paid']
    assert failures == []


def test_row_translations_still_missing_after_retry_stay_english(monkeypatch):
    class StubbornSarvam:
        def translate_many(self, texts, language, **_kwargs):
            return {'Paid': '[hi] Paid'} if 'Paid' in texts else {}
    monkeypatch.setattr(query_router, 'SarvamClient', StubbornSarvam)
    failures = []
    result = query_router._localize_rows([{'s': 'Paid'}, {'s': 'Due'}], 'hi-IN', failures=failures)
    assert result == [{'s': '[hi] Paid'}, {'s': 'Due'}]
    assert failures == ['Due']
