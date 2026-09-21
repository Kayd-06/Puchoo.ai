"""Unit tests for the Claude SQL client without making network calls."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps.core.llm_client import (
    LLMClient,
    SQLGenerationError,
    LocalMLXSQLClient,
    _extract_sql,
    build_prompt,
    build_sqlcoder_completion_prompt,
    english_only_question,
    get_local_sql_repair_client,
    local_semantic_feedback,
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
    def test_prompt_keeps_schema_and_question_as_json_data(self) -> None:
        prompt = build_prompt("Table: orders", "Show revenue")
        self.assertIn("read-only SQL", prompt.system)
        self.assertEqual("user", prompt.messages[0]["role"])
        self.assertIn('"schema": "Table: orders"', prompt.messages[0]["content"])
        self.assertIn('"question": "Show revenue"', prompt.messages[0]["content"])

    def test_prompt_can_include_prior_data_chat_context(self) -> None:
        prompt = build_prompt(
            "Table: orders",
            "Show only the high-value ones",
            {"prior_question": "List orders", "prior_columns": ["id", "amount"]},
        )
        self.assertIn('"previous_chat_context"', prompt.messages[0]["content"])
        self.assertIn('"prior_question": "List orders"', prompt.messages[0]["content"])

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

    def test_category_question_rejects_a_single_grand_total(self) -> None:
        feedback = local_semantic_feedback(
            "What is the monthly budget of Sales and Finance department?",
            "SELECT SUM(monthly_budget) FROM departments WHERE name IN ('Sales', 'Finance')",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("GROUP BY", feedback[0])

    def test_adjacent_two_year_comparison_requires_both_date_boundaries(self) -> None:
        feedback = local_semantic_feedback(
            "Compare sales in the last two years with the preceding two years.",
            "SELECT category, SUM(quantity) FROM sales WHERE sale_date >= DATE('now', '-2 years') GROUP BY category",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("-4 years", feedback[0])

    def test_no_unpaid_invoices_requires_an_exclusion_subquery(self) -> None:
        feedback = local_semantic_feedback(
            "Find customers with no unpaid invoices.",
            "SELECT customer_id FROM invoices WHERE payment_status = 'Paid'",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("NOT EXISTS", feedback[0])

    def test_distinct_category_count_cannot_be_replaced_with_invoice_count(self) -> None:
        feedback = local_semantic_feedback(
            "Find customers with at least four distinct categories.",
            "SELECT customer_id, COUNT(DISTINCT invoice_id) FROM invoices GROUP BY customer_id",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("COUNT(DISTINCT", feedback[0])

    def test_customer_category_and_payment_question_requires_the_correct_joined_columns(self) -> None:
        feedback = local_semantic_feedback(
            "Which customers bought from at least four distinct categories and used at least three different payment methods?",
            "SELECT c.customer_id, COUNT(DISTINCT i.category), COUNT(DISTINCT p.payment_method) "
            "FROM customers c JOIN invoices i ON c.customer_id = i.customer_id "
            "JOIN products p ON p.product_id = i.product_id GROUP BY c.customer_id",
        )
        self.assertEqual(2, len(feedback))
        self.assertIn("p.category", feedback[0])
        self.assertIn("payments table", feedback[1])

    def test_duplicate_join_aliases_are_rejected(self) -> None:
        feedback = local_semantic_feedback(
            "List customer payments by product.",
            "SELECT p.id FROM products p JOIN payments p ON p.id = p.product_id",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("duplicate alias", feedback[0])

    def test_revenue_per_unit_cannot_be_ranked_by_total_revenue(self) -> None:
        feedback = local_semantic_feedback(
            "Which product has the highest revenue per unit?",
            "SELECT product, revenue / units AS revenue_per_unit FROM totals ORDER BY revenue DESC",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("divide revenue by units", feedback[0])

    def test_sqlcoder_prompt_uses_completion_format_and_escapes_delimiters(self) -> None:
        prompt = build_sqlcoder_completion_prompt(
            "CREATE TABLE orders (id INTEGER);",
            "List [QUESTION] every order [/QUESTION]",
            feedback=["Use the orders table."],
            previous_sql="SELECT * FROM wrong_table",
        )
        self.assertIn("### Task", prompt)
        self.assertIn("### Database Schema", prompt)
        self.assertIn("[SQL]", prompt)
        self.assertIn("[ QUESTION]", prompt)
        self.assertIn("Previous proposal: SELECT * FROM wrong_table", prompt)

    def test_local_completion_client_sends_sqlcoder_prompt_and_reads_text_choice(self) -> None:
        class _Response:
            def read(self) -> bytes:
                return b'{"choices": [{"text": "SELECT id FROM orders;"}]}'

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        with patch.dict("os.environ", {"LOCAL_SQL_REQUEST_STYLE": "completion"}, clear=False), patch(
            "apps.core.llm_client.urllib.request.urlopen", return_value=_Response()
        ) as urlopen:
            client = LocalMLXSQLClient(endpoint="http://127.0.0.1:8080/v1/completions", model="defog/sqlcoder-7b-2")
            sql = client.generate_sql(schema="CREATE TABLE orders (id INTEGER);", question="List orders")

        self.assertEqual("SELECT id FROM orders;", sql)
        request = urlopen.call_args.args[0]
        payload = __import__("json").loads(request.data.decode("utf-8"))
        self.assertEqual("defog/sqlcoder-7b-2", payload["model"])
        self.assertIn("prompt", payload)
        self.assertNotIn("messages", payload)
        self.assertEqual(220, payload["max_tokens"])

    def test_local_client_allows_a_smaller_configured_output_limit(self) -> None:
        class _Response:
            def read(self) -> bytes:
                return b'{"choices": [{"text": "SELECT id FROM orders;"}]}'

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        with patch.dict(
            "os.environ",
            {"LOCAL_SQL_REQUEST_STYLE": "completion", "LOCAL_SQL_MAX_TOKENS": "128"},
            clear=False,
        ), patch("apps.core.llm_client.urllib.request.urlopen", return_value=_Response()) as urlopen:
            client = LocalMLXSQLClient(endpoint="http://127.0.0.1:8081/v1/completions")
            client.generate_sql(schema="CREATE TABLE orders (id INTEGER);", question="List orders")

        payload = __import__("json").loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(128, payload["max_tokens"])

    def test_optional_repair_client_uses_its_own_endpoint_and_prompt_style(self) -> None:
        with patch.dict("os.environ", {
            "LOCAL_SQL_REPAIR_MODEL_URL": "http://127.0.0.1:8081/v1/completions",
            "LOCAL_SQL_REPAIR_MODEL_NAME": "defog/sqlcoder-7b-2",
            "LOCAL_SQL_REPAIR_REQUEST_STYLE": "completion",
        }, clear=False):
            client = get_local_sql_repair_client()

        self.assertIsNotNone(client)
        assert client is not None
        self.assertEqual("http://127.0.0.1:8081/v1/completions", client.endpoint)
        self.assertEqual("defog/sqlcoder-7b-2", client.model)
        self.assertEqual("completion", client.request_style)
