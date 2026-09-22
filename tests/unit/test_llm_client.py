"""Unit tests for the Claude SQL client without making network calls."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps.core.llm_client import (
    LLMClient,
    LocalMLXSQLClient,
    SQLGenerationError,
    _extract_sql,
    build_prompt,
    get_local_sql_repair_client,
    english_only_question,
    local_semantic_feedback,
    question_clarification,
    compact_plan_feedback,
    schema_guided_fallback_sql,
)


class _FakeMessages:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text=self.content)])


class _FakeClient:
    def __init__(self, content: str | None) -> None:
        self.messages = _FakeMessages(content)


class LLMClientTests(unittest.TestCase):
    def test_doing_well_students_requests_performance_definition(self) -> None:
        result = question_clarification(
            "Table: students\nColumns: student_id, marks, attendance_percentage",
            "Show me the students who are doing well.",
        )
        self.assertEqual("ambiguous_education_metric", result["reason"])

    def test_better_attendance_requests_comparison_baseline(self) -> None:
        result = question_clarification(
            "Table: attendance\nColumns: student_id, attendance_percentage",
            "Show students with better attendance",
        )
        self.assertEqual("missing_comparison_baseline", result["reason"])

    def test_promotion_eligibility_requests_policy(self) -> None:
        result = question_clarification(
            "Table: students\nColumns: student_id, marks",
            "Show students eligible for promotion",
        )
        self.assertEqual("missing_policy_definition", result["reason"])

    def test_ambiguous_ranking_requests_a_metric(self) -> None:
        result = question_clarification("Table: customers\nColumns: revenue", "Who are our best customers?")
        self.assertEqual("ambiguous_metric", result["reason"])

    def test_fiscal_period_requests_start_month(self) -> None:
        result = question_clarification("Table: sales", "Compare this fiscal year with last fiscal year")
        self.assertEqual("missing_time_definition", result["reason"])

    def test_absent_business_concept_is_explained(self) -> None:
        result = question_clarification("Table: customers\nColumns: customer_id, name", "Show customer churn")
        self.assertEqual("concept_not_in_data", result["reason"])

    def test_explicit_complex_metric_does_not_require_clarification(self) -> None:
        result = question_clarification("Table: sales\nColumns: revenue, sale_date", "Top products by revenue over the rolling 90 days")
        self.assertIsNone(result)

    def test_cte_plan_error_becomes_actionable_feedback(self) -> None:
        feedback = compact_plan_feedback(
            RuntimeError("no such column: total_revenue [SQL: ...]"),
            "WITH totals AS (SELECT SUM(amount) AS total_revenue FROM sales) SELECT total_revenue",
        )
        self.assertIn("FROM the correct CTE", feedback)

    def test_window_alias_error_explains_sqlite_scope_rule(self) -> None:
        feedback = compact_plan_feedback(
            RuntimeError("no such column: total_sales [SQL: ...]"),
            "SELECT SUM(amount) AS total_sales, RANK() OVER (ORDER BY total_sales DESC) FROM sales",
        )
        self.assertIn("window ORDER BY", feedback)
        self.assertIn("repeat the aggregate expression", feedback)

    def test_prompt_keeps_schema_and_question_as_json_data(self) -> None:
        prompt = build_prompt("Table: orders", "Show revenue")
        self.assertIn("read-only SQL", prompt.system)
        self.assertEqual("user", prompt.messages[0]["role"])
        self.assertIn('"schema": "Table: orders"', prompt.messages[0]["content"])
        self.assertIn('"question": "User question: Show revenue', prompt.messages[0]["content"])

    def test_client_uses_claude_messages_and_returns_sql(self) -> None:
        fake_client = _FakeClient("```sql\nSELECT id FROM orders\n```")
        client = LLMClient(client=fake_client, model="test-model")
        sql = client.generate_sql(schema="Table: orders", question="List ids")
        self.assertEqual("SELECT id FROM orders", sql)
        self.assertEqual("test-model", fake_client.messages.kwargs["model"])
        self.assertIn("system", fake_client.messages.kwargs)

    def test_empty_model_response_is_rejected(self) -> None:
        client = LLMClient(client=_FakeClient(None))
        with self.assertRaises(SQLGenerationError):
            client.generate_sql(schema="Table: orders", question="List ids")

    def test_extract_sql_removes_local_chat_end_marker(self) -> None:
        self.assertEqual(
            "SELECT id FROM orders;",
            _extract_sql("SELECT id FROM orders;<|im_end|>"),
        )

    def test_english_only_question_rejects_indic_script(self) -> None:
        with self.assertRaises(SQLGenerationError):
            english_only_question("मुझे सभी छात्रों को दिखाओ")

    def test_invoice_status_feedback_requires_case_normalization(self) -> None:
        feedback = local_semantic_feedback(
            "Show all unpaid invoices ordered by total amount from highest to lowest.",
            "SELECT * FROM invoices WHERE payment_status = 'Unpaid'",
        )
        self.assertEqual(["Filter unpaid invoices with LOWER(payment_status) = 'unpaid'."], feedback)

    def test_overall_attendance_requires_average_and_having(self) -> None:
        feedback = local_semantic_feedback(
            "List students with overall attendence greater than 75 percent.",
            "SELECT name, attendance_percentage FROM attendance WHERE attendance_percentage > 75",
        )
        self.assertEqual(2, len(feedback))
        self.assertIn("AVG", feedback[0])
        self.assertIn("HAVING", feedback[1])

    def test_average_in_cte_can_be_filtered_by_alias(self) -> None:
        feedback = local_semantic_feedback(
            "List students with overall attendance greater than 75 percent",
            "WITH totals AS (SELECT student_id, AVG(attendance_percentage) AS attendance_average "
            "FROM attendance GROUP BY student_id) SELECT * FROM totals WHERE attendance_average > 75",
        )
        self.assertEqual([], feedback)

    def test_pending_bill_requires_outstanding_invoice_statuses(self) -> None:
        feedback = local_semantic_feedback(
            "List customers having pending bill payment",
            "SELECT c.customer_name FROM customers c JOIN payments p ON p.customer_id = c.customer_id WHERE p.payment_status = 'Pending'",
            "Table: sales_invoices_sales_invoices",
        )
        self.assertEqual(2, len(feedback))
        self.assertIn("sales-invoices", feedback[0])
        self.assertIn("unpaid", feedback[1])

    def test_outstanding_summary_requires_separate_invoice_status_counts(self) -> None:
        feedback = local_semantic_feedback(
            "Show unpaid invoice count, partial invoice count, total billed, total paid, and outstanding balance",
            "SELECT COUNT(ii.invoice_item_id), SUM(ii.line_total) FROM sales_invoices si "
            "JOIN invoice_items ii ON ii.invoice_id = si.invoice_id "
            "WHERE LOWER(si.payment_status) IN ('unpaid', 'partial')",
            "Table: sales_invoices\nTable: invoice_items\nTable: payments",
        )
        self.assertTrue(any("separately" in item for item in feedback))
        self.assertFalse(any("Filter partial invoices" in item for item in feedback))

    def test_customer_summary_rejects_scalar_invoice_totals_and_active_filter(self) -> None:
        feedback = local_semantic_feedback(
            "Top customers by outstanding invoice balance with unpaid invoice count, partial invoice count, total billed, total paid, and remaining balance",
            "SELECT SUM(CASE WHEN LOWER(s.payment_status)='unpaid' THEN 1 ELSE 0 END) AS unpaid_invoice_count, "
            "SUM(CASE WHEN LOWER(s.payment_status)='partial' THEN 1 ELSE 0 END) AS partial_invoice_count, "
            "s.total_amount AS total_billed_amount, COALESCE(p.amount_paid,0) AS total_paid_amount, "
            "s.total_amount-COALESCE(p.amount_paid,0) AS remaining_balance FROM customers c "
            "JOIN sales_invoices s ON s.customer_id=c.customer_id LEFT JOIN payments p ON p.invoice_id=s.invoice_id "
            "WHERE LOWER(c.status)='active' GROUP BY c.customer_id",
            "Table: sales_invoices\nTable: payments\nTable: customers",
        )
        self.assertTrue(any("payment_totals CTE" in item for item in feedback))
        self.assertTrue(any("active customers" in item for item in feedback))

    def test_outstanding_customer_summary_has_schema_guided_fallback(self) -> None:
        schema = """Table: customers\nColumns: customer_id (INTEGER), customer_name (TEXT)

Table: invoices\nColumns: invoice_id (INTEGER), customer_id (INTEGER), total_amount (INTEGER), payment_status (TEXT)

Table: payments\nColumns: payment_id (INTEGER), invoice_id (INTEGER), amount_paid (INTEGER)"""
        sql = schema_guided_fallback_sql(
            schema,
            "Top customers by outstanding invoice balance with unpaid invoice count, partial invoice count, "
            "total billed amount, total paid amount, and remaining balance",
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("WITH payment_totals", sql)
        self.assertIn("SUM(i.total_amount)", sql)
        self.assertNotIn("invoice_items", sql)

    def test_never_received_invoice_requires_an_absence_query(self) -> None:
        feedback = local_semantic_feedback(
            "List active customers who never received an invoice",
            "SELECT * FROM customers WHERE customer_id NOT IN (SELECT customer_id FROM invoices WHERE status = 'Paid')",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("NOT EXISTS", feedback[0])

    def test_best_selling_uses_invoice_items_not_inventory_movements(self) -> None:
        feedback = local_semantic_feedback(
            "Show the best-selling products by total quantity",
            "SELECT product_id, SUM(quantity) FROM inventory_movements GROUP BY product_id",
            "Table: invoice_items_invoice_items",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("invoice_items.quantity", feedback[0])

    def test_rolling_window_requires_a_date_filter(self) -> None:
        feedback = local_semantic_feedback(
            "Show revenue over the rolling 90 days",
            "SELECT SUM(total_amount) FROM invoices",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("rolling window", feedback[0])

    def test_completion_client_reads_sqlcoder_text_response(self) -> None:
        class _Response:
            def read(self) -> bytes:
                return b'{"choices": [{"text": "SELECT id FROM orders;"}]}'

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        with patch("apps.core.llm_client.urllib.request.urlopen", return_value=_Response()) as urlopen:
            client = LocalMLXSQLClient(
                endpoint="http://127.0.0.1:8081/v1/completions",
                model="defog/sqlcoder-7b-2",
                request_style="completion",
            )
            sql = client.generate_sql(schema="CREATE TABLE orders (id INTEGER);", question="List orders")

        self.assertEqual("SELECT id FROM orders;", sql)
        payload = __import__("json").loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertIn("prompt", payload)
        self.assertNotIn("messages", payload)

    def test_optional_repair_client_uses_configured_completion_endpoint(self) -> None:
        with patch.dict("os.environ", {
            "LOCAL_SQL_REPAIR_MODEL_URL": "http://127.0.0.1:8081/v1/completions",
            "LOCAL_SQL_REPAIR_MODEL_NAME": "defog/sqlcoder-7b-2",
            "LOCAL_SQL_REPAIR_REQUEST_STYLE": "completion",
        }, clear=False):
            client = get_local_sql_repair_client()
        self.assertIsNotNone(client)
        assert client is not None
        self.assertEqual("completion", client.request_style)
