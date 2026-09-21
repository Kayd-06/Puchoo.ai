"""Tests for AST-backed SQL validation and outer-limit clamping."""

from __future__ import annotations

import unittest

try:
    import sqlglot  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - dependency-free test environments
    sqlglot = None

from apps.core.guardrails import SQLGuardrailError, SQLGuardrails, validate_data_question


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

    def test_rejects_literal_only_answers(self) -> None:
        for sql in (
            "SELECT 'The prime minister of India is Narendra Modi' AS result",
            "SELECT 'The prime minister of India is Narendra Modi' AS result FROM orders",
        ):
            with self.subTest(sql=sql), self.assertRaises(SQLGuardrailError):
                self.guardrails.validate(sql)

    def test_allows_data_derived_queries(self) -> None:
        self.assertIn("FROM orders", self.guardrails.validate("SELECT id FROM orders"))
        self.assertIn("COUNT(*)", self.guardrails.validate("SELECT COUNT(*) FROM orders"))

    def test_blocks_general_knowledge_question_outside_the_schema(self) -> None:
        with self.assertRaisesRegex(SQLGuardrailError, "only answers questions grounded"):
            validate_data_question("Who is the prime minister of India?", "Table: expenses\nColumns: amount (INTEGER), expense_date (DATE)")

    def test_blocks_external_market_question_even_when_product_is_in_the_schema(self) -> None:
        with self.assertRaisesRegex(SQLGuardrailError, "outside the uploaded data"):
            validate_data_question(
                "What product should I launch next based on current market trends outside this uploaded data?",
                "Table: products\nColumns: product_id (INTEGER), product_name (TEXT), category (TEXT)",
            )

    def test_blocks_an_unrelated_aggregate_question(self) -> None:
        with self.assertRaises(SQLGuardrailError):
            validate_data_question("What is the highest mountain in the world?", "Table: expenses\nColumns: amount (INTEGER), expense_date (DATE)")

    def test_allows_question_grounded_in_schema(self) -> None:
        validate_data_question("What is the total monthly budget by department?", "Table: departments\nColumns: department (TEXT), monthly_budget (INTEGER)")

    def test_allows_human_words_that_match_underscored_schema_identifiers(self) -> None:
        validate_data_question(
            "Give me the unit price with line total and discount from invoice items.",
            "Table: invoice_items\nColumns: unit_price (REAL), line_total (REAL), discount (REAL)",
        )
