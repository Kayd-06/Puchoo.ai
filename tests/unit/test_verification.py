"""Tests for verifier JSON handling without an Anthropic network call."""

from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from apps.core.verification import ClaudeVerifier, VerificationStatus


class _Messages:
    def __init__(self, response: str) -> None:
        self.response = response

    def create(self, **_: object) -> object:
        return SimpleNamespace(content=[SimpleNamespace(text=self.response)])


class _Client:
    def __init__(self, response: str) -> None:
        self.messages = _Messages(response)


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
