"""Tests for AST-backed SQL validation and outer-limit clamping."""

from __future__ import annotations

import unittest

try:
    import sqlglot  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - dependency-free test environments
    sqlglot = None

from apps.core.guardrails import SQLGuardrailError, SQLGuardrails


@unittest.skipIf(sqlglot is None, "sqlglot is not installed")
class SQLGuardrailsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.guardrails = SQLGuardrails(max_limit=100)

    def test_adds_an_outer_limit_when_one_is_missing(self) -> None:
        guarded = self.guardrails.validate_and_clamp("SELECT id FROM orders")
        self.assertIn("LIMIT 100", guarded.sql)
        self.assertEqual(100, guarded.limit)

    def test_clamps_only_the_outer_limit(self) -> None:
        guarded = self.guardrails.validate_and_clamp(
            "SELECT * FROM (SELECT id FROM orders LIMIT 5) AS recent LIMIT 999"
        )
        self.assertIn("LIMIT 5", guarded.sql)
        self.assertTrue(guarded.sql.rstrip().endswith("LIMIT 100"))

    def test_preserves_a_smaller_outer_limit(self) -> None:
        guarded = self.guardrails.validate_and_clamp("SELECT id FROM orders LIMIT 25")
        self.assertIn("LIMIT 25", guarded.sql)
        self.assertEqual(25, guarded.limit)

    def test_rejects_multiple_or_non_select_statements(self) -> None:
        for sql in (
            "SELECT id FROM orders; DELETE FROM orders",
            "DELETE FROM orders",
            "SELECT * INTO backup_orders FROM orders",
        ):
            with self.subTest(sql=sql), self.assertRaises(SQLGuardrailError):
                self.guardrails.validate(sql)

    def test_rejects_data_changing_cte(self) -> None:
        with self.assertRaises(SQLGuardrailError):
            self.guardrails.validate(
                "WITH deleted AS (DELETE FROM orders RETURNING id) SELECT * FROM deleted"
            )
