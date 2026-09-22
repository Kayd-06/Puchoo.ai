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

    def test_pending_bill_requires_outstanding_invoice_statuses(self) -> None:
        feedback = local_semantic_feedback(
            "List customers having pending bill payment",
            "SELECT c.customer_name FROM customers c JOIN payments p ON p.customer_id = c.customer_id WHERE p.payment_status = 'Pending'",
            "Table: sales_invoices_sales_invoices",
        )
        self.assertEqual(2, len(feedback))
        self.assertIn("sales-invoices", feedback[0])
        self.assertIn("unpaid", feedback[1])

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
