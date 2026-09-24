"""Regression tests for malformed model output at the tokenizer boundary."""

from __future__ import annotations

import unittest

from apps.core.guardrails import SQLGuardrailError, SQLGuardrails


class GuardrailTokenErrorTests(unittest.TestCase):
    def test_unclosed_identifier_is_reported_as_guardrail_error(self) -> None:
        with self.assertRaises(SQLGuardrailError):
            SQLGuardrails().validate_and_clamp('SELECT * FROM `broken')


if __name__ == "__main__":
    unittest.main()
