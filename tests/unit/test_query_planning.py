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

    def test_arbitrary_rank_alias_does_not_trigger_global_limit_repair(self):
        plan = StructuredQueryPlan(normalized_question="For each class show the three lowest students including ties", relevant_tables=["students"], ranking={"direction": "ascending", "limit": 3})
        for alias in ("rnk", "attendance_position", '"rank position"'):
            sql = f"WITH ranked AS (SELECT student_id, RANK() OVER (PARTITION BY class_name ORDER BY attendance) AS {alias} FROM students) SELECT * FROM ranked AS r WHERE r.{alias} <= 3 ORDER BY student_id"
            with self.subTest(alias=alias):
                self.assertEqual([], plan_constraint_feedback(plan, sql))

    def test_partitioned_ranking_rejects_global_limit_and_missing_rank_filter(self):
        plan = StructuredQueryPlan(normalized_question="For each class show three students", relevant_tables=["students"], ranking={"limit": 3})
        base = "WITH ranked AS (SELECT student_id, RANK() OVER (PARTITION BY class_name ORDER BY attendance) AS rnk FROM students) SELECT * FROM ranked"
        feedback = plan_constraint_feedback(plan, base + " WHERE rnk <= 3 ORDER BY student_id LIMIT 3")
        self.assertTrue(any("global LIMIT" in item for item in feedback))
        feedback = plan_constraint_feedback(plan, base + " ORDER BY student_id")
        self.assertTrue(any("rank" in item for item in feedback))
        self.assertFalse(any("add LIMIT" in item for item in feedback))

    def test_global_ranking_still_requires_limit(self):
        plan = StructuredQueryPlan(normalized_question="Show the top three students", relevant_tables=["students"], ranking={"limit": 3})
        self.assertTrue(any("add LIMIT" in item for item in plan_constraint_feedback(plan, "SELECT * FROM students ORDER BY attendance")))

    def test_untokenizable_model_sql_returns_feedback_instead_of_raising(self):
        # An unterminated quote raises sqlglot's TokenError, not ParseError.
        # The guardrail must report it so the repair loop can run.
        plan = StructuredQueryPlan(normalized_question="For each class show three students", relevant_tables=["students"], ranking={"limit": 3})
        feedback = plan_constraint_feedback(plan, "SELECT class_name, 'unterminated FROM students ORDER BY 1")
        self.assertIsInstance(feedback, list)

    def test_partitioned_rank_bound_accepts_both_orientations_and_between(self):
        plan = StructuredQueryPlan(normalized_question="For each class show three students", relevant_tables=["students"], ranking={"limit": 3})
        base = "WITH ranked AS (SELECT student_id, DENSE_RANK() OVER (PARTITION BY class_name ORDER BY attendance) AS pos FROM students) SELECT * FROM ranked AS r WHERE "
        for where in ("r.pos <= 3", "pos < 4", "3 >= pos", "4 > r.pos", "pos BETWEEN 1 AND 3", "(pos <= 3) AND student_id > 0"):
            with self.subTest(where=where):
                self.assertEqual([], plan_constraint_feedback(plan, base + where + " ORDER BY student_id"))
        for where in ("pos <= 5", "5 >= pos", "pos BETWEEN 2 AND 3", "pos <= 3 OR pos IS NULL", "pos >= 3"):
            with self.subTest(where=where):
                feedback = plan_constraint_feedback(plan, base + where + " ORDER BY student_id")
                self.assertTrue(any("top N per group" in item for item in feedback))

    def test_numeric_string_ranking_limit_is_coerced(self):
        payload = valid_payload()
        payload["ranking"] = {"direction": "descending", "limit": "3"}
        plan = parse_plan_json(json.dumps(payload), schema=SCHEMA, original_question="Top three customers")
        self.assertEqual(3, plan.ranking["limit"])
        sql = ("WITH ranked AS (SELECT customer_id, ROW_NUMBER() OVER (PARTITION BY region ORDER BY total_amount DESC) AS rn "
               "FROM customers) SELECT * FROM ranked WHERE rn <= 3 ORDER BY customer_id")
        self.assertFalse(any("top N" in item for item in plan_constraint_feedback(plan, sql)))

    def test_invalid_ranking_limit_is_rejected(self):
        for limit in ("three", -1, 0, 2.5, True, "3; DROP"):
            payload = valid_payload()
            payload["ranking"] = {"direction": "descending", "limit": limit}
            with self.subTest(limit=limit), self.assertRaises(QueryPlanError):
                parse_plan_json(json.dumps(payload), schema=SCHEMA, original_question="Top customers")


if __name__ == "__main__":
    unittest.main()

class CompletePlanContextTests(unittest.TestCase):
    def test_required_tables_are_not_silently_dropped(self):
        plan = StructuredQueryPlan(**valid_payload())
        with patch.dict('os.environ', {'LOCAL_SQL_SCHEMA_MAX_TABLES': '2'}):
            with self.assertRaises(QueryPlanError):
                select_plan_schema(SCHEMA, plan)

class DirectAnswerPlanTests(unittest.TestCase):
    def test_missing_data_is_an_explicit_non_query_outcome(self):
        payload = {**valid_payload(), 'answer_status': 'unavailable', 'limitations': ['Campaign dates and attribution are not recorded.'], 'unavailable_reason': 'Campaign profit cannot be determined from this data.'}
        plan = parse_plan_json(json.dumps(payload), schema=SCHEMA, original_question='Did the campaign cause more profit?')
        self.assertEqual('unavailable', plan.answer_status)
        self.assertIn('Campaign dates', plan.limitations[0])

    def test_unavailable_outcome_requires_a_direct_explanation(self):
        for reason in (None, '', 25):
            with self.subTest(reason=reason), self.assertRaises(QueryPlanError):
                parse_plan_json(json.dumps({**valid_payload(), 'answer_status': 'unavailable', 'unavailable_reason': reason}), schema=SCHEMA, original_question='x')

    def test_partial_answer_requires_disclosed_limitations(self):
        with self.assertRaises(QueryPlanError):
            parse_plan_json(json.dumps({**valid_payload(), 'answer_status': 'partial'}), schema=SCHEMA, original_question='x')

    def test_planner_gets_current_date_and_one_bounded_retry_for_defaults(self):
        calls = []
        class Client:
            def generate_plan(self, **kwargs):
                calls.append(kwargs['question'])
                return json.dumps({**valid_payload(), 'needs_clarification': len(calls) == 1, 'clarification_question': 'Net or total sales?' if len(calls) == 1 else None, 'assumptions': ['Sales uses total_amount; all recorded dates.']})
        plan = plan_complex_query(Client(), schema=SCHEMA, question='Compare regional sales')
        self.assertFalse(plan.needs_clarification)
        self.assertEqual(2, len(calls))
        self.assertIn('Server reference date:', calls[0])
        self.assertIn('Net or total sales?', calls[1])


class RankFilterTests(unittest.TestCase):
    def _plan(self, limit):
        return parse_plan_json(json.dumps({**valid_payload(), 'ranking': {'direction': 'desc', 'limit': limit}}), schema=SCHEMA, original_question='x')

    def test_rank_equals_one_bounds_top_one_per_group(self):
        sql = "WITH r AS (SELECT a, ROW_NUMBER() OVER (PARTITION BY b ORDER BY c DESC) AS rn FROM t) SELECT a FROM r WHERE rn = 1"
        feedback = plan_constraint_feedback(self._plan(1), sql)
        self.assertFalse([item for item in feedback if 'partitioned rank' in item])
        reversed_sql = sql.replace('rn = 1', '1 = rn')
        self.assertFalse([item for item in plan_constraint_feedback(self._plan(1), reversed_sql) if 'partitioned rank' in item])

    def test_rank_equals_one_does_not_satisfy_top_three(self):
        sql = "WITH r AS (SELECT a, ROW_NUMBER() OVER (PARTITION BY b ORDER BY c DESC) AS rn FROM t) SELECT a FROM r WHERE rn = 1"
        self.assertTrue([item for item in plan_constraint_feedback(self._plan(3), sql) if 'partitioned rank' in item])
