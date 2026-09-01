"""Tests for the UI MVP's deterministic demo/query safety boundary."""

import unittest

from apps.ui.data.demo_data import execute_demo_query, generate_demo_query


class DemoQueryTests(unittest.TestCase):
    def test_sales_question_is_proposed_but_not_executed(self) -> None:
        query = generate_demo_query("How has monthly revenue changed over the last six months?")

        self.assertEqual(query["status"], "approved")
        self.assertFalse(query["executed"])
        self.assertIn("SELECT", query["sql"])
        self.assertIn("LIMIT 500;", query["sql"])
        self.assertGreater(query["confidence"], 0)

    def test_write_request_is_blocked_before_sql_execution(self) -> None:
        query = generate_demo_query("Delete every cancelled order")

        self.assertEqual(query["status"], "blocked")
        self.assertFalse(query["executed"])
        self.assertIn("Blocked", query["guardrail_message"])

    def test_execution_requires_an_explicit_second_step(self) -> None:
        proposed = generate_demo_query("Revenue by region")
        executed = execute_demo_query(proposed)

        self.assertFalse(proposed["executed"])
        self.assertTrue(executed["executed"])
        self.assertEqual(executed["status"], "executed")

    def test_blocked_query_cannot_be_marked_as_executed(self) -> None:
        blocked = generate_demo_query("Drop the orders table")

        with self.assertRaisesRegex(ValueError, "Only an approved query"):
            execute_demo_query(blocked)

    def test_each_proposal_has_a_unique_audit_id(self) -> None:
        first = generate_demo_query("Revenue by region")
        second = generate_demo_query("Revenue by region")

        self.assertNotEqual(first["id"], second["id"])

    def test_additional_high_risk_request_words_are_blocked(self) -> None:
        query = generate_demo_query("Grant analyst access to every table")

        self.assertEqual(query["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
