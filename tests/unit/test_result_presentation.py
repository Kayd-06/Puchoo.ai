"""Tests for deterministic, user-facing result presentation."""

from __future__ import annotations

import unittest

from apps.core.result_presentation import build_result_presentation


class ResultPresentationTests(unittest.TestCase):
    def test_single_aggregate_has_a_plain_language_headline_and_metric(self) -> None:
        result = build_result_presentation(
            "How much revenue came from Furniture?",
            ["revenue"],
            [{"revenue": 229500}],
        )
        self.assertEqual("Revenue: 229,500", result.headline)
        self.assertEqual([("Revenue", "229,500")], result.highlights)

    def test_multiple_rows_describe_the_result_count(self) -> None:
        result = build_result_presentation(
            "Show unpaid invoices.",
            ["customer_name", "total_amount"],
            [{"customer_name": "A", "total_amount": 10}, {"customer_name": "B", "total_amount": 20}],
        )
        self.assertEqual("Found 2 matching results.", result.headline)
        self.assertEqual([("Matching results", "2")], result.highlights)

    def test_empty_result_is_explained_without_claiming_an_answer(self) -> None:
        result = build_result_presentation("Show missing values.", ["name"], [])
        self.assertEqual("No matching data was found.", result.headline)
        self.assertEqual([], result.highlights)
