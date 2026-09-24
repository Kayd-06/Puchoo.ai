"""Focused tests for complex routing, planning, retrieval, and prompts."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.core.query_planning import (
    QueryPlanError,
    StructuredQueryPlan,
    build_plan_sql_request,
    classify_complexity,
    parse_plan_json,
    plan_complex_query,
    plan_constraint_feedback,
    select_plan_schema,
)


SCHEMA = """Table: customers
Columns: customer_id (INTEGER), customer_name (TEXT)

Table: invoices
Columns: invoice_id (INTEGER), customer_id (INTEGER), invoice_date (TEXT), total_amount (REAL)

Table: payments
Columns: payment_id (INTEGER), invoice_id (INTEGER), amount_paid (REAL)

Table: unrelated
Columns: note_id (INTEGER), note (TEXT)"""


def valid_payload() -> dict[str, object]:
    return {
        "normalized_question": "Rank customers by unpaid balance over the rolling 90 days.",
        "relevant_tables": ["customers", "invoices", "payments"],
        "metrics": ["SUM(total_amount - amount_paid) AS unpaid_balance"],
        "filters": [],
        "time_range": "rolling 90 days",
        "group_by": ["customers.customer_id", "customers.customer_name"],
        "ranking": {"direction": "descending", "limit": 10},
        "joins": [{"left": "invoices.customer_id", "right": "customers.customer_id"}],
        "assumptions": ["Missing payment rows count as zero paid."],
        "needs_clarification": False,
        "clarification_question": None,
    }


class QueryPlanningTests(unittest.TestCase):
    def test_simple_question_keeps_fast_route(self) -> None:
        self.assertEqual("simple", classify_complexity("List all customers", SCHEMA).route)

    def test_multi_metric_time_ranking_question_is_planned(self) -> None:
        decision = classify_complexity(
            "Compare customer revenue and invoice count over the rolling 90 days and show the top 10.", SCHEMA
        )
        self.assertEqual("planned", decision.route)
        self.assertIn("multiple_metrics", decision.reasons)

    def test_plan_parser_rejects_invalid_json_and_unknown_tables(self) -> None:
        with self.assertRaises(QueryPlanError):
            parse_plan_json("not json", schema=SCHEMA, original_question="x")
        payload = valid_payload()
        payload["relevant_tables"] = ["invented_table"]
        with self.assertRaisesRegex(QueryPlanError, "unknown tables"):
            parse_plan_json(json.dumps(payload), schema=SCHEMA, original_question="x")

    def test_pdf_singular_metric_and_period_fields_are_normalized(self) -> None:
        payload = valid_payload()
        payload["metric"] = payload.pop("metrics")[0]
        payload["period"] = payload.pop("time_range")
        plan = parse_plan_json(json.dumps(payload), schema=SCHEMA, original_question="x")
        self.assertEqual(["SUM(total_amount - amount_paid) AS unpaid_balance"], plan.metrics)
        self.assertEqual("rolling 90 days", plan.time_range)

    def test_planner_clarification_requires_a_question(self) -> None:
        payload = valid_payload()
        payload["needs_clarification"] = True
        with self.assertRaisesRegex(QueryPlanError, "without a question"):
            parse_plan_json(json.dumps(payload), schema=SCHEMA, original_question="x")

    def test_complex_planner_uses_client_json(self) -> None:
        class Client:
            def generate_plan(self, **_kwargs: str) -> str:
                return json.dumps(valid_payload())
        plan = plan_complex_query(Client(), schema=SCHEMA, question="complex")
        self.assertEqual(["customers", "invoices", "payments"], plan.relevant_tables)

    def test_schema_selection_is_bounded_and_excludes_unrelated_table(self) -> None:
        plan = StructuredQueryPlan(**valid_payload())
        with patch.dict("os.environ", {"LOCAL_SQL_SCHEMA_MAX_TABLES": "3", "LOCAL_SQL_SCHEMA_MAX_CHARS": "4000"}):
            focused, tables = select_plan_schema(SCHEMA, plan)
        self.assertEqual(["customers", "invoices", "payments"], tables)
        self.assertNotIn("Table: unrelated", focused)

    def test_empty_table_plan_uses_bounded_lexical_fallback(self) -> None:
        payload = valid_payload()
        payload["relevant_tables"] = []
        payload["normalized_question"] = "List invoice totals by customer"
        plan = StructuredQueryPlan(**payload)
        with patch.dict("os.environ", {"LOCAL_SQL_SCHEMA_MAX_TABLES": "2", "LOCAL_SQL_SCHEMA_MAX_CHARS": "4000"}):
            _focused, tables = select_plan_schema(SCHEMA, plan)
        self.assertLessEqual(len(tables), 2)
        self.assertIn("invoices", tables)

    def test_generation_request_preserves_original_question_and_plan(self) -> None:
        plan = StructuredQueryPlan(**valid_payload())
        request = build_plan_sql_request("Original multi-part wording", plan)
        self.assertIn("Original multi-part wording", request)
        self.assertIn("rolling 90 days", request)
        self.assertIn("SQLite SQL only", request)

    def test_constraint_feedback_detects_lost_grouping_and_ranking(self) -> None:
        plan = StructuredQueryPlan(**valid_payload())
        feedback = plan_constraint_feedback(plan, "SELECT total_amount FROM invoices")
        self.assertTrue(any("GROUP BY" in item for item in feedback))
        self.assertTrue(any("ORDER BY" in item for item in feedback))

    def test_partitioned_top_n_does_not_require_global_limit(self) -> None:
        plan = StructuredQueryPlan(**valid_payload())
        sql = (
            "WITH ranked AS (SELECT customer_id, unpaid_balance, "
            "ROW_NUMBER() OVER (PARTITION BY region ORDER BY unpaid_balance DESC) AS rn "
            "FROM customers) SELECT * FROM ranked WHERE rn <= 10 ORDER BY unpaid_balance DESC"
        )
        feedback = plan_constraint_feedback(plan, sql)
        self.assertFalse(any("LIMIT" in item for item in feedback))


if __name__ == "__main__":
    unittest.main()
