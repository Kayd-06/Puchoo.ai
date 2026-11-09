"""Tests for verifier JSON handling without an Anthropic network call."""

from __future__ import annotations

import pytest

import json
from types import SimpleNamespace
import unittest

from apps.core.verification import ClaudeVerifier, GroqVerifier, VerificationStatus


class _Messages:
    def __init__(self, response: str) -> None:
        self.response = response

    def create(self, **_: object) -> object:
        return SimpleNamespace(content=[SimpleNamespace(text=self.response)])


class _Client:
    def __init__(self, response: str) -> None:
        self.messages = _Messages(response)


class _GroqClient:
    def __init__(self, response: str) -> None:
        self.response = response

    def _chat(self, **_: object) -> str:
        return self.response


class ClaudeVerifierTests(unittest.TestCase):
    def test_match_is_exposed_as_verified(self) -> None:
        payload = json.dumps({"verdict": "MATCH", "confidence": 93, "summary": "Matches.", "details": "Checked."})
        result = ClaudeVerifier(client=_Client(payload)).verify(
            question="What is the amount?", sql="SELECT amount FROM metrics", columns=["amount"], rows=[{"amount": 10}], row_count=1
        )
        self.assertEqual(VerificationStatus.VERIFIED, result.status)
        self.assertEqual(93, result.confidence)

    def test_mismatch_is_not_normalized_to_success(self) -> None:
        payload = json.dumps({"verdict": "MISMATCH", "confidence": 82, "summary": "Different measure.", "details": "The grouping is wrong."})
        result = ClaudeVerifier(client=_Client(payload)).verify(
            question="Count rows", sql="SELECT amount FROM metrics", columns=["amount"], rows=[{"amount": 10}], row_count=1
        )
        self.assertEqual(VerificationStatus.VERIFICATION_MISMATCH, result.status)

    def test_groq_fallback_exposes_a_verified_result(self) -> None:
        payload = json.dumps({"verdict": "MATCH", "confidence": 91, "summary": "Matches.", "details": "Checked."})
        result = GroqVerifier(client=_GroqClient(payload)).verify(
            question="What is the amount?", sql="SELECT amount FROM metrics", columns=["amount"], rows=[{"amount": 10}], row_count=1
        )
        self.assertEqual(VerificationStatus.VERIFIED, result.status)
        self.assertEqual(91, result.confidence)


@pytest.mark.parametrize('provider', ['claude', 'groq'])
def test_provider_exception_details_are_not_public(provider):
    from types import SimpleNamespace
    from apps.core.verification import ClaudeVerifier, GroqVerifier, verification_unavailable
    private = 'SYNTHETIC_SECRET_742 https://private.invalid/internal'
    def fail(**kwargs):
        raise RuntimeError(private)
    client = SimpleNamespace(messages=SimpleNamespace(create=fail), _chat=fail)
    verifier = ClaudeVerifier(client=client) if provider == 'claude' else GroqVerifier(client=client)
    result = verifier.verify(question='total', sql='SELECT 1', columns=['n'], rows=[{'n': 1}], row_count=1).as_dict()
    assert result['status'] == 'UNAVAILABLE'
    assert 'SYNTHETIC_SECRET' not in str(result) and 'private.invalid' not in str(result)
    assert private not in str(verification_unavailable(private).as_dict())
