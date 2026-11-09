"""Unit tests for the Claude SQL client without making network calls."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from apps.core.llm_client import (
    DeepSeekSQLClient,
    LLMClient,
    LocalMLXSQLClient,
    SQLGenerationError,
    _extract_sql,
    build_prompt,
    english_only_question,
    local_semantic_feedback,
    question_clarification,
    compact_plan_feedback,
    canonicalize_analytics_question,
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
    def test_deepseek_planner_uses_json_mode_and_safe_headers(self) -> None:
        class _Response:
            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"{}"}}]}'

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        with patch("apps.core.llm_client.urllib.request.urlopen", return_value=_Response()) as urlopen:
            client = DeepSeekSQLClient(api_key="test-secret", model="test-model")
            client.generate_plan(schema="Table: orders\nColumns: id (INTEGER)", question="List orders")
        request = urlopen.call_args.args[0]
        payload = __import__("json").loads(request.data.decode("utf-8"))
        self.assertEqual({"type": "json_object"}, payload["response_format"])
        self.assertEqual("https://api.deepseek.com/chat/completions", request.full_url)
        self.assertIn("only", payload["messages"][0]["content"])
        self.assertEqual("PuchooAI/1.0", request.headers["User-agent"])
        self.assertNotIn("test-secret", request.data.decode("utf-8"))

    def test_deepseek_retries_only_transient_generation_rejection(self):
        import io
        import urllib.error
        response = __import__('contextlib').nullcontext(SimpleNamespace(read=lambda: b'{"choices":[{"message":{"content":"SELECT 1"}}]}'))
        error = urllib.error.HTTPError('https://example.invalid', 400, 'bad request', {}, io.BytesIO(b'{"error":{"code":"json_validate_failed","message":"private schema must not be logged"}}'))
        with patch('apps.core.llm_client.urllib.request.urlopen', side_effect=[error, response]) as send:
            answer = DeepSeekSQLClient(api_key='test-secret')._chat(system='JSON', user='synthetic request')
        self.assertEqual(answer, 'SELECT 1')
        self.assertEqual(send.call_count, 2)

    def test_deepseek_generation_retry_is_bounded_and_never_uses_failed_output(self):
        import io
        import urllib.error
        errors = [urllib.error.HTTPError('https://example.invalid', 400, 'bad request', {}, io.BytesIO(b'{"error":{"code":"structured_generation_failed","failed_generation":"SELECT private_data"}}')) for _ in range(2)]
        with patch('apps.core.llm_client.urllib.request.urlopen', side_effect=errors) as send:
            with self.assertRaises(SQLGenerationError):
                DeepSeekSQLClient(api_key='test-secret')._chat(system='SQL', user='synthetic request')
        self.assertEqual(send.call_count, 2)

    def test_deepseek_invalid_settings_are_not_retried_or_exposed(self):
        import io
        import urllib.error
        from apps.core.llm_client import LocalMLXConfigurationError
        error = urllib.error.HTTPError('https://example.invalid', 400, 'bad request', {}, io.BytesIO(b'{"error":{"code":"invalid_request_error","message":"secret-private-content"}}'))
        with patch('apps.core.llm_client.urllib.request.urlopen', side_effect=error) as send:
            with self.assertRaises(LocalMLXConfigurationError) as raised:
                DeepSeekSQLClient(api_key='test-secret')._chat(system='SQL', user='synthetic request')
        self.assertEqual(send.call_count, 1)
        self.assertEqual(raised.exception.provider_error_code, 'invalid_request_error')
        self.assertNotIn('secret-private-content', str(raised.exception))

    def test_student_trend_classification_requests_rules_and_periods(self) -> None:
        result = question_clarification(
            "Table: students\nColumns: student_id\n\nTable: grades\nColumns: student_id, marks_obtained",
            "Compare each student's current academic performance with previous performance and attendance trend, then classify each student as improving, stable, or declining.",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("missing_performance_classification_definition", result["reason"])
        self.assertIn("periods", result["message"])
        self.assertIn("score change", result["message"])

    def test_defined_student_trend_classification_can_proceed(self) -> None:
        result = question_clarification(
            "Table: students\nColumns: student_id\n\nTable: grades\nColumns: student_id, marks_obtained",
            "Compare average marks and attendance in the latest 90 days with the prior 90 days; "
            "classify at least +5 points as improving, at most -5 as declining, otherwise stable.",
        )
        self.assertIsNone(result)

    def test_fee_and_enrollment_role_in_classification_is_clarified(self) -> None:
        result = question_clarification(
            "Table: students\nColumns: student_id",
            "Compare student marks, attendance, fee-payment behavior, and enrollment status, then classify "
            "them as improving, stable, or declining. Compare the latest 90 days with the prior 90 days; "
            "classify at least +5 points as improving and at most -5 as declining.",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual("missing_classification_factor_rules", result["reason"])

    def test_display_only_fee_and_enrollment_rule_can_proceed(self) -> None:
        result = question_clarification(
            "Table: students\nColumns: student_id",
            "Compare marks and attendance in the latest 90 days with the prior 90 days; classify at least +5 "
            "points as improving and at most -5 as declining. Classify using marks and attendance only; "
            "show fee-payment behavior and enrollment status separately.",
        )
        self.assertIsNone(result)
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

    def test_ambiguous_column_error_requires_table_qualification(self) -> None:
        feedback = compact_plan_feedback(
            RuntimeError("ambiguous column name: course_id [SQL: ...]"),
            "SELECT course_id FROM courses c JOIN enrollments e ON c.course_id=e.course_id",
        )
        self.assertIn("ambiguous", feedback)
        self.assertIn("alias.course_id", feedback)

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

    def test_attendance_below_threshold_uses_student_average(self):
        schema = "Table: students\nColumns: student_id (INTEGER), full_name (TEXT)\n\nTable: attendance\nColumns: student_id (INTEGER), attendance_percentage (REAL)"
        connection = sqlite3.connect(":memory:")
        connection.executescript("CREATE TABLE students(student_id INTEGER, full_name TEXT); CREATE TABLE attendance(student_id INTEGER, attendance_percentage REAL); INSERT INTO students VALUES (1,'Asha'),(2,'Rohan'),(3,'Mira'); INSERT INTO attendance VALUES (1,60),(1,100),(2,60),(2,80),(3,75);")
        for wording, expected in (("less than", [(2, "Rohan", 70.0)]), ("below", [(2, "Rohan", 70.0)]), ("at most", [(3, "Mira", 75.0), (2, "Rohan", 70.0)])):
            with self.subTest(wording=wording):
                question = f"Give me the list of students having attendance {wording} 75%."
                interpreted = canonicalize_analytics_question(question)
                self.assertIn("overall attendance", interpreted)
                sql = schema_guided_fallback_sql(schema, question)
                self.assertIsNotNone(sql)
                self.assertEqual(expected, connection.execute(sql).fetchall())
        connection.close()

    def test_attendance_shortcut_preserves_extra_constraints(self):
        schema = "Table: students\nColumns: student_id (INTEGER), full_name (TEXT)\n\nTable: attendance\nColumns: student_id (INTEGER), attendance_percentage (REAL)"
        for question in ("List students with attendance below 75% last month", "List students in class 10 with attendance below 75%", "List students with each attendance record below 75%"):
            self.assertEqual(question, canonicalize_analytics_question(question))
            self.assertIsNone(schema_guided_fallback_sql(schema, question))

    def test_overall_attendance_threshold_has_executable_schema_guided_fallback(self) -> None:
        schema = """Table: _02_students_students
Columns: student_id (INTEGER), full_name (TEXT)

Table: _06_attendance_attendance
Columns: attendance_id (INTEGER), student_id (INTEGER), attendance_date (TEXT), attendance_percentage (REAL)"""
        question = "Give me the list of students having overall attendance greater than 70 percent"

        sql = schema_guided_fallback_sql(schema, question)

        self.assertIsNotNone(sql)
        assert sql is not None
        connection = sqlite3.connect(":memory:")
        connection.executescript(
            """
            CREATE TABLE _02_students_students (student_id INTEGER, full_name TEXT);
            CREATE TABLE _06_attendance_attendance (
                attendance_id INTEGER,
                student_id INTEGER,
                attendance_date TEXT,
                attendance_percentage REAL
            );
            INSERT INTO _02_students_students VALUES (1, 'Asha'), (2, 'Rohan');
            INSERT INTO _06_attendance_attendance VALUES
                (1, 1, '2026-01-01', 80),
                (2, 1, '2026-01-02', 70),
                (3, 2, '2026-01-01', 69),
                (4, 2, '2026-01-02', 70);
            """
        )
        rows = connection.execute(sql).fetchall()
        connection.close()

        self.assertEqual([(1, "Asha", 75.0)], rows)
        self.assertEqual([], local_semantic_feedback(question, sql, schema))

    def test_attendence_threshold_without_overall_has_executable_fallback(self) -> None:
        schema = """Table: _02_students_students
Columns: student_id (INTEGER), full_name (TEXT)

Table: _06_attendance_attendance
Columns: attendance_id (INTEGER), student_id (INTEGER), attendance_date (TEXT), attendance_percentage (REAL)"""
        question = "give me the list of students having attendence greater than 70 percent"

        sql = schema_guided_fallback_sql(schema, question)

        self.assertIsNotNone(sql)
        assert sql is not None
        connection = sqlite3.connect(":memory:")
        connection.executescript(
            """
            CREATE TABLE _02_students_students (student_id INTEGER, full_name TEXT);
            CREATE TABLE _06_attendance_attendance (
                attendance_id INTEGER,
                student_id INTEGER,
                attendance_date TEXT,
                attendance_percentage REAL
            );
            INSERT INTO _02_students_students VALUES (1, 'Asha'), (2, 'Rohan');
            INSERT INTO _06_attendance_attendance VALUES
                (1, 1, '2026-01-01', 80),
                (2, 1, '2026-01-02', 70),
                (3, 2, '2026-01-01', 69),
                (4, 2, '2026-01-02', 70);
            """
        )
        rows = connection.execute(sql).fetchall()
        connection.close()

        self.assertEqual([(1, "Asha", 75.0)], rows)
        self.assertEqual([], local_semantic_feedback(question, sql, schema))

    def test_average_cte_alias_can_be_compared_on_right_side(self) -> None:
        feedback = local_semantic_feedback(
            "Show students with fee balance above the class average",
            "WITH balances AS (SELECT class_name, SUM(amount_due-amount_paid) AS balance FROM fees "
            "GROUP BY class_name), class_avg AS (SELECT AVG(balance) AS avg_balance FROM balances) "
            "SELECT * FROM balances b JOIN class_avg a ON 1=1 WHERE b.balance > a.avg_balance",
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

    def test_defined_student_marks_attendance_trend_has_deterministic_fallback(self) -> None:
        schema = """Table: students
Columns: student_id (INTEGER), full_name (TEXT)

Table: attendance
Columns: attendance_id (INTEGER), student_id (INTEGER), attendance_date (TEXT), attendance_percentage (REAL)

Table: assessments
Columns: assessment_id (INTEGER), assessment_date (TEXT), maximum_marks (INTEGER)

Table: grades
Columns: grade_id (INTEGER), student_id (INTEGER), assessment_id (INTEGER), marks_obtained (INTEGER)

Table: fees
Columns: fee_id (INTEGER), student_id (INTEGER), amount_due (REAL), amount_paid (REAL), payment_status (TEXT)

Table: enrollments
Columns: enrollment_id (INTEGER), student_id (INTEGER), enrollment_date (TEXT), enrollment_status (TEXT)"""
        question = (
            "Compare each student average marks percentage and attendance percentage in the latest 90 days "
            "with the prior 90 days; average both changes, classify at least +5 points as improving, "
            "at most -5 as declining, otherwise stable."
            " Classify using marks and attendance only; show fee-payment behavior and enrollment status separately."
        )
        sql = schema_guided_fallback_sql(schema, question)
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("100.0 * g.marks_obtained", sql)
        self.assertIn("'-180 days'", sql)
        self.assertIn("AS trend_classification", sql)
        self.assertIn("fee_payment_behavior", sql)
        self.assertIn("enrollment_status", sql)
        self.assertEqual([], local_semantic_feedback(question, sql, schema))

    def test_comprehensive_student_dashboard_has_deterministic_fallback(self) -> None:
        schema = """Table: students
Columns: student_id (INTEGER), full_name (TEXT), class_name (TEXT)

Table: assessments
Columns: assessment_id (INTEGER), course_id (INTEGER), maximum_marks (INTEGER)

Table: grades
Columns: student_id (INTEGER), assessment_id (INTEGER), marks_obtained (INTEGER), result_status (TEXT)

Table: attendance
Columns: student_id (INTEGER), attendance_percentage (REAL)

Table: fees
Columns: student_id (INTEGER), amount_due (REAL), amount_paid (REAL)

Table: loans
Columns: student_id (INTEGER), loan_status (TEXT)"""
        question = (
            "For every student, calculate average marks, marks relative to the course average, overall attendance, "
            "attendance relative to the class average, total fees due, total paid, unpaid balance, failed assessment "
            "count, overdue library-loan count, and rank students using marks, attendance, and unpaid balance."
        )
        sql = schema_guided_fallback_sql(schema, question)
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("a.assessment_id = g.assessment_id", sql)
        self.assertIn("SUM(f.amount_due - f.amount_paid)", sql)
        self.assertIn("ROW_NUMBER() OVER", sql)
        self.assertEqual([], local_semantic_feedback(question, sql, schema))

    def test_student_marks_percentage_uses_name_and_maximum_marks(self) -> None:
        schema = """Table: students
Columns: student_id (INTEGER), full_name (TEXT)

Table: assessments
Columns: assessment_id (INTEGER), assessment_name (TEXT), maximum_marks (INTEGER)

Table: grades
Columns: grade_id (INTEGER), student_id (INTEGER), assessment_id (INTEGER), marks_obtained (INTEGER)"""
        question = "Tell me which students scored marks greater than 80 percent and give their marks and name"
        sql = schema_guided_fallback_sql(schema, question)
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("s.full_name AS student_name", sql)
        self.assertIn("100.0 * g.marks_obtained / NULLIF(a.maximum_marks, 0)", sql)
        self.assertIn("> 80", sql)
        self.assertEqual([], local_semantic_feedback(question, sql, schema))

    def test_wrong_id_alias_and_raw_mark_threshold_are_rejected(self) -> None:
        schema = """Table: students
Columns: student_id (INTEGER), full_name (TEXT)
Table: assessments
Columns: assessment_id (INTEGER), maximum_marks (INTEGER)
Table: grades
Columns: student_id (INTEGER), assessment_id (INTEGER), marks_obtained (INTEGER)"""
        feedback = local_semantic_feedback(
            "Which students scored marks greater than 80 percent? Give marks and name",
            "SELECT g.student_id AS student_name, g.marks_obtained FROM grades g WHERE g.marks_obtained > 80",
            schema,
        )
        self.assertTrue(any("percentage" in item for item in feedback))
        self.assertTrue(any("full_name" in item for item in feedback))

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

    def test_equivalent_top_product_wording_has_one_canonical_intent(self) -> None:
        singular = canonicalize_analytics_question(
            "Please tell me which item sold the most in my shop last month."
        )
        plural = canonicalize_analytics_question(
            "Please tell me which items sold the most in my shop last month."
        )
        self.assertEqual(singular, plural)
        self.assertEqual(
            "Which product sold the most by total quantity during the previous calendar month?",
            singular,
        )

    def test_top_product_last_month_has_deterministic_schema_fallback(self) -> None:
        schema = """Table: products
Columns: product_id (INTEGER), product_name (TEXT), category (TEXT)

Table: invoice_items
Columns: invoice_item_id (INTEGER), invoice_id (INTEGER), product_id (INTEGER), quantity (INTEGER)

Table: sales_invoices
Columns: invoice_id (INTEGER), invoice_date (TEXT), customer_id (INTEGER)"""
        sql = schema_guided_fallback_sql(
            schema,
            "Which product sold the most by total quantity during the previous calendar month?",
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("SUM(ii.quantity) AS total_quantity_sold", sql)
        self.assertIn("date(si.invoice_date)", sql)
        self.assertIn("ORDER BY total_quantity_sold DESC, p.product_id ASC", sql)
        self.assertTrue(sql.rstrip().endswith("LIMIT 1"))

    def test_monthly_expenses_by_category_uses_expense_fields_and_totals(self) -> None:
        schema = """Table: _03_products_products
Columns: product_id (INTEGER), product_name (TEXT), category (TEXT)

Table: _09_expenses_expenses
Columns: expense_id (INTEGER), expense_date (TEXT), expense_category (TEXT), amount (REAL)"""
        question = "give my monthly expenses category wise"

        sql = schema_guided_fallback_sql(schema, question)

        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("FROM _09_expenses_expenses AS e", sql)
        self.assertIn("strftime('%Y-%m', e.expense_date) AS expense_month", sql)
        self.assertIn("e.expense_category", sql)
        self.assertIn("SUM(e.amount) AS total_expenses", sql)
        self.assertNotIn("_03_products_products", sql)

        connection = sqlite3.connect(":memory:")
        connection.executescript(
            """
            CREATE TABLE _09_expenses_expenses (
                expense_id INTEGER, expense_date TEXT, expense_category TEXT, amount REAL
            );
            INSERT INTO _09_expenses_expenses VALUES
                (1, '2026-01-03', 'Rent', 1000),
                (2, '2026-01-12', 'Supplies', 200),
                (3, '2026-01-20', 'Rent', 500),
                (4, '2026-02-02', 'Rent', 900);
            """
        )
        rows = connection.execute(sql).fetchall()
        connection.close()
        self.assertEqual(
            [("2026-01", "Rent", 1500.0), ("2026-01", "Supplies", 200.0), ("2026-02", "Rent", 900.0)],
            rows,
        )

    def test_rolling_window_requires_a_date_filter(self) -> None:
        feedback = local_semantic_feedback(
            "Show revenue over the rolling 90 days",
            "SELECT SUM(total_amount) FROM invoices",
        )
        self.assertEqual(1, len(feedback))
        self.assertIn("rolling window", feedback[0])

    def test_completion_only_sqlcoder_style_is_rejected(self) -> None:
        with self.assertRaisesRegex(Exception, "must be 'chat'"):
            LocalMLXSQLClient(request_style="completion")

    def test_local_default_output_cap_supports_complex_sql(self) -> None:
        with patch.dict("os.environ", {"LOCAL_SQL_MAX_TOKENS": "450"}, clear=False):
            client = LocalMLXSQLClient(request_style="chat")
        self.assertEqual(450, client.max_tokens)

    def test_qwen_repair_prompt_contains_previous_sql_and_database_error(self) -> None:
        class _Response:
            def read(self) -> bytes:
                return b'{"choices": [{"message": {"content": "SELECT id FROM orders"}}]}'

            def __enter__(self) -> "_Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        with patch("apps.core.llm_client.urllib.request.urlopen", return_value=_Response()) as urlopen:
            client = LocalMLXSQLClient(request_style="chat")
            sql = client.generate_sql(
                schema="Table: orders\nColumns: id (INTEGER)",
                question="Original question plus structured plan",
                previous_sql="SELECT missing FROM orders",
                feedback=["Exact database error: no such column: missing"],
            )
        self.assertEqual("SELECT id FROM orders", sql)
        payload = __import__("json").loads(urlopen.call_args.args[0].data.decode("utf-8"))
        prompt = payload["messages"][1]["content"]
        self.assertIn("SELECT missing FROM orders", prompt)
        self.assertIn("no such column: missing", prompt)
        self.assertNotIn("prompt", payload)

class GroundedStudentQueries(unittest.TestCase):
    def test_unpaid_fees_uses_actual_balances_and_excludes_paid_students(self):
        schema = 'Table: pupils\nColumns: student_id (INTEGER), full_name (TEXT)\n\nTable: charges\nColumns: student_id (INTEGER), amount_due (REAL), amount_paid (REAL)'
        sql = schema_guided_fallback_sql(schema, 'give me the list of students with unpaid fee')
        self.assertIsNotNone(sql)
        db = sqlite3.connect(':memory:')
        db.executescript("CREATE TABLE pupils(student_id,full_name); CREATE TABLE charges(student_id,amount_due,amount_paid); INSERT INTO pupils VALUES(1,'Partial'),(2,'Paid'),(3,'Credit and debt'); INSERT INTO charges VALUES(1,100,40),(2,100,100),(3,100,120),(3,100,50);")
        self.assertEqual(db.execute(sql).fetchall(), [(1, 'Partial', 60), (3, 'Credit and debt', 50)])
        db.close()

    def test_unpaid_fees_fallback_does_not_discard_extra_constraints(self):
        schema = 'Table: pupils\nColumns: student_id (INTEGER), full_name (TEXT)\n\nTable: charges\nColumns: student_id (INTEGER), amount_due (REAL), amount_paid (REAL)'
        self.assertIsNone(schema_guided_fallback_sql(schema, 'list students with unpaid fees in class 10 last month'))

    def test_constant_false_query_is_not_treated_as_an_answer(self):
        feedback = local_semantic_feedback('list students with unpaid fee', 'SELECT full_name FROM pupils WHERE 0 = 1', 'Table: pupils\nColumns: full_name (TEXT)')
        self.assertTrue(any('constant' in item.lower() for item in feedback))

    def test_attendance_fallback_does_not_ignore_class_or_date_filters(self):
        schema = 'Table: pupils\nColumns: student_id (INTEGER), full_name (TEXT), class_name (TEXT)\n\nTable: presence\nColumns: student_id (INTEGER), attendance_percentage (REAL), attendance_date (TEXT)'
        self.assertIsNone(schema_guided_fallback_sql(schema, 'List students in class 10 with attendance above 75 percent last month'))

    def test_paid_fees_uses_disclosed_full_payment_default(self):
        schema = 'Table: students\nColumns: student_id,full_name\nTable: fees\nColumns: student_id,amount_due,amount_paid'
        question = canonicalize_analytics_question('give me the list of students with paid fee')
        self.assertIn('fully paid all recorded fees', question)
        self.assertIsNone(question_clarification(schema, question))
        sql = schema_guided_fallback_sql(schema, question)
        self.assertIn('f.amount_due > COALESCE(f.amount_paid, 0)', sql)
        self.assertIn('f.amount_due IS NULL', sql)
        import sqlite3
        connection = sqlite3.connect(':memory:')
        connection.executescript("""
            CREATE TABLE students(student_id INTEGER, full_name TEXT);
            CREATE TABLE fees(student_id INTEGER, amount_due REAL, amount_paid REAL);
            INSERT INTO students VALUES (1,'Settled'),(2,'Partial'),(3,'Overpaid elsewhere'),(4,'Unknown'),(5,'No fees');
            INSERT INTO fees VALUES (1,100,100),(2,100,50),(3,100,200),(3,100,0),(4,NULL,100);
        """)
        self.assertEqual(connection.execute(sql).fetchall(), [(1, 'Settled')])
        connection.close()
        self.assertEqual(canonicalize_analytics_question('list students with paid fees in class 10'), 'list students with paid fees in class 10')

    def test_explicit_partial_payment_lookup_is_grounded_without_model(self):
        question = canonicalize_analytics_question('give me the list of student with paid fee. . Students who have made any payment, including partial payments')
        schema = 'Table: students\nColumns: student_id,full_name\nTable: fees\nColumns: student_id,amount_due,amount_paid'
        sql = schema_guided_fallback_sql(schema, question)
        self.assertIsNotNone(sql)
        connection = sqlite3.connect(':memory:')
        connection.executescript("CREATE TABLE students(student_id, full_name); CREATE TABLE fees(student_id,amount_due,amount_paid); INSERT INTO students VALUES (1,'Paid'),(2,'Partial'),(3,'Unpaid'); INSERT INTO fees VALUES (1,100,100),(2,100,30),(3,100,0);")
        self.assertEqual(connection.execute(sql).fetchall(), [(1,'Paid'),(2,'Partial')])
        connection.close()
        self.assertIsNone(schema_guided_fallback_sql(schema, 'List students who have made any payment, including partial payments last month'))

    def test_unpaid_feedback_does_not_invent_different_schema_columns(self):
        schema = 'Table: learners\nColumns: id (INTEGER), name (TEXT)\nTable: dues\nColumns: learner_id (INTEGER), billed (REAL), received (REAL)'
        feedback = local_semantic_feedback('List students with unpaid fees', 'SELECT l.name FROM learners l JOIN dues d ON d.learner_id=l.id WHERE d.billed > d.received', schema)
        self.assertFalse(any('amount_due' in item for item in feedback))


class DeepSeekReasoningEffortTests(unittest.TestCase):
    def _payload(self, model: str) -> dict:
        class _Response:
            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"SELECT 1"}}]}'

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        with patch("apps.core.llm_client.urllib.request.urlopen", return_value=_Response()) as urlopen:
            DeepSeekSQLClient(api_key="k", model=model)._chat(system="s", user="u")
        return __import__("json").loads(urlopen.call_args.args[0].data.decode("utf-8"))

    def test_flash_disables_thinking_for_bounded_sql_output(self):
        payload = self._payload("deepseek-flash")
        self.assertEqual({"type": "disabled"}, payload["thinking"])
        self.assertNotIn("reasoning_effort", payload)
        self.assertIn("Never invent", payload["messages"][0]["content"])

    def test_default_provider_and_model(self):
        from apps.core.llm_client import get_sql_client
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=True), patch("dotenv.load_dotenv"):
            client = get_sql_client()
        self.assertIsInstance(client, DeepSeekSQLClient)
        self.assertEqual("deepseek-flash", client.model)
        self.assertEqual("deepseek-flash", client.planner_model)

    def test_missing_key_fails_without_using_old_provider(self):
        from apps.core.llm_client import LocalMLXConfigurationError
        with patch.dict("os.environ", {"GROQ_API_KEY": "obsolete"}, clear=True), patch("dotenv.load_dotenv"):
            with self.assertRaisesRegex(LocalMLXConfigurationError, "DEEPSEEK_API_KEY"):
                DeepSeekSQLClient()

    def test_removed_groq_provider_names_deepseek_settings(self):
        from apps.core.llm_client import SQLProviderConfigurationError, get_sql_client
        env = {"PUCHOO_SQL_PROVIDER": "groq", "GROQ_API_KEY": "obsolete", "DEEPSEEK_API_KEY": "test-key"}
        with patch.dict("os.environ", env, clear=True), patch("dotenv.load_dotenv"), \
                patch("apps.core.llm_client.urllib.request.urlopen", side_effect=AssertionError("no provider call")):
            with self.assertRaises(SQLProviderConfigurationError) as raised:
                get_sql_client()
        detail = raised.exception.public_detail
        self.assertIn("PUCHOO_SQL_PROVIDER=deepseek", detail)
        self.assertIn("DEEPSEEK_API_KEY", detail)
        self.assertNotIn("obsolete", detail)
        self.assertNotIn("test-key", detail)

    def test_unknown_provider_is_a_clear_configuration_error(self):
        from apps.core.llm_client import SQLProviderConfigurationError, get_sql_client
        with patch.dict("os.environ", {"PUCHOO_SQL_PROVIDER": "openai"}, clear=True), patch("dotenv.load_dotenv"):
            with self.assertRaisesRegex(SQLProviderConfigurationError, "deepseek, local, or claude"):
                get_sql_client()

    def test_missing_deepseek_key_is_actionable(self):
        from apps.core.llm_client import SQLProviderConfigurationError, get_sql_client
        for env in ({}, {"PUCHOO_SQL_PROVIDER": ""}, {"PUCHOO_SQL_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "  "}):
            with self.subTest(env=env), patch.dict("os.environ", env, clear=True), patch("dotenv.load_dotenv"):
                with self.assertRaises(SQLProviderConfigurationError) as raised:
                    get_sql_client()
                self.assertIn("DEEPSEEK_API_KEY is not set", raised.exception.public_detail)

    def test_partial_or_empty_output_is_rejected(self):
        import contextlib
        import json
        for choice in (
            {"finish_reason": "length", "message": {"content": "SELECT"}},
            {"finish_reason": "stop", "message": {"content": "   "}},
        ):
            response = contextlib.nullcontext(SimpleNamespace(read=lambda: json.dumps({"choices": [choice]}).encode()))
            with patch("apps.core.llm_client.urllib.request.urlopen", return_value=response):
                with self.assertRaises(SQLGenerationError):
                    DeepSeekSQLClient(api_key="test").generate_sql(schema="Table: orders\nColumns: id (INTEGER)", question="List orders")
