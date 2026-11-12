"""Regression: the reported expenses + receivables questions are answerable as separate analyses.

Realistic model SQL (CTEs, ROW_NUMBER = 1, LAG, correlated subqueries and a
window AVG per region) must pass the guard and the semantic checks.
"""
import json
import sqlite3

import pytest

from apps.core.executor import ReadOnlyExecutor
from apps.core.llm_client import local_semantic_feedback, question_clarification
from apps.core.query_planning import parse_plan_json, plan_constraint_feedback

SCHEMA = """Table: customers_customers
Columns: customer_id (INTEGER), customer_name (TEXT), region (TEXT), status (TEXT)

Table: expenses_expenses
Columns: expense_id (INTEGER), category (TEXT), expense_date (TEXT), amount (INTEGER)

Table: sales_invoices_sales_invoices
Columns: invoice_id (INTEGER), customer_id (INTEGER), invoice_date (TEXT), total_amount (INTEGER), payment_status (TEXT)

Table: payments_payments
Columns: payment_id (INTEGER), invoice_id (INTEGER), payment_date (TEXT), amount_paid (INTEGER)"""
Q1 = "For each month in the last year, which expense category accounted for the largest share of total expenses, and in which months did that category's spending increase even though total monthly expenses decreased from the previous month?"
Q2 = "Among customers with an unpaid invoice, which have made payments totaling more than half of their total invoiced amount but still owe more than the average outstanding balance of customers in their region? Include partially paid invoices and show how much each customer owes."
SQL1 = """WITH monthly AS (
  SELECT strftime('%Y-%m', e.expense_date) AS month, e.category, SUM(e.amount) AS category_total
  FROM expenses_expenses e
  WHERE e.expense_date >= date('2026-11-12', '-12 months')
  GROUP BY month, e.category
), totals AS (
  SELECT month, SUM(category_total) AS month_total FROM monthly GROUP BY month
), ranked AS (
  SELECT m.month, m.category, m.category_total, t.month_total,
         ROW_NUMBER() OVER (PARTITION BY m.month ORDER BY m.category_total DESC) AS rn
  FROM monthly m JOIN totals t ON t.month = m.month
), changes AS (
  SELECT r.month, r.category, r.category_total, r.month_total,
         LAG(r.month_total) OVER (ORDER BY r.month) AS prev_month_total,
         (SELECT m2.category_total FROM monthly m2 WHERE m2.category = r.category AND m2.month = (SELECT MAX(m3.month) FROM monthly m3 WHERE m3.month < r.month)) AS prev_category_total
  FROM ranked r WHERE r.rn = 1
)
SELECT month, category, category_total, ROUND(100.0 * category_total / month_total, 2) AS share_pct,
       month_total, prev_month_total, prev_category_total,
       CASE WHEN category_total > prev_category_total AND month_total < prev_month_total THEN 1 ELSE 0 END AS increased_while_total_fell
FROM changes ORDER BY month"""
SQL2 = """WITH paid AS (
  SELECT p.invoice_id, SUM(p.amount_paid) AS paid_amount FROM payments_payments p GROUP BY p.invoice_id
), customer_balances AS (
  SELECT c.customer_id, c.customer_name, c.region,
         SUM(si.total_amount) AS total_invoiced,
         SUM(COALESCE(pd.paid_amount, 0)) AS total_paid,
         SUM(si.total_amount - COALESCE(pd.paid_amount, 0)) AS outstanding_balance,
         SUM(CASE WHEN LOWER(si.payment_status) = 'unpaid' THEN 1 ELSE 0 END) AS unpaid_invoices
  FROM customers_customers c
  JOIN sales_invoices_sales_invoices si ON si.customer_id = c.customer_id
  LEFT JOIN paid pd ON pd.invoice_id = si.invoice_id
  WHERE LOWER(si.payment_status) IN ('unpaid', 'partial')
  GROUP BY c.customer_id, c.customer_name, c.region
), with_region AS (
  SELECT cb.*, AVG(cb.outstanding_balance) OVER (PARTITION BY cb.region) AS region_avg_outstanding
  FROM customer_balances cb
)
SELECT customer_name, region, total_invoiced, total_paid, outstanding_balance, region_avg_outstanding
FROM with_region
WHERE unpaid_invoices > 0 AND total_paid > 0.5 * total_invoiced AND outstanding_balance > region_avg_outstanding
ORDER BY outstanding_balance DESC"""
SQL2B = SQL2.replace("""), with_region AS (
  SELECT cb.*, AVG(cb.outstanding_balance) OVER (PARTITION BY cb.region) AS region_avg_outstanding
  FROM customer_balances cb
)""", """), region_avg AS (
  SELECT region, AVG(outstanding_balance) AS region_avg_outstanding FROM customer_balances GROUP BY region
), with_region AS (
  SELECT cb.*, ra.region_avg_outstanding FROM customer_balances cb JOIN region_avg ra ON ra.region = cb.region
)""")


@pytest.fixture
def executor(tmp_path):
    path = tmp_path / "business.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE customers_customers(customer_id INTEGER, customer_name TEXT, region TEXT, status TEXT);"
        "CREATE TABLE expenses_expenses(expense_id INTEGER, category TEXT, expense_date TEXT, amount INTEGER);"
        "CREATE TABLE sales_invoices_sales_invoices(invoice_id INTEGER, customer_id INTEGER, invoice_date TEXT, total_amount INTEGER, payment_status TEXT);"
        "CREATE TABLE payments_payments(payment_id INTEGER, invoice_id INTEGER, payment_date TEXT, amount_paid INTEGER);"
    )
    connection.close()
    return ReadOnlyExecutor(f"sqlite:///{path}")


@pytest.mark.parametrize("question", [Q1, Q2])
def test_reported_questions_need_no_clarification(question):
    assert question_clarification(SCHEMA, question) is None


@pytest.mark.parametrize(("question", "sql"), [(Q1, SQL1), (Q2, SQL2), (Q2, SQL2B)])
def test_realistic_sql_passes_guard_and_semantic_checks(executor, question, sql):
    executor.validate_query_plan(sql)
    assert local_semantic_feedback(question, sql, SCHEMA) == []


def test_top_category_per_month_plan_accepts_rank_equals_one():
    plan = parse_plan_json(json.dumps({
        "normalized_question": Q1, "relevant_tables": ["expenses_expenses"],
        "metrics": ["category expense share", "month-over-month change"], "filters": [],
        "time_range": "last 12 months", "group_by": ["month", "category"],
        "ranking": {"direction": "desc", "limit": 1}, "joins": [], "assumptions": [],
        "needs_clarification": False, "clarification_question": None,
    }), schema=SCHEMA, original_question=Q1)
    assert plan_constraint_feedback(plan, SQL1) == []


def test_receivables_plan_accepts_window_average_per_region():
    plan = parse_plan_json(json.dumps({
        "normalized_question": Q2,
        "relevant_tables": ["customers_customers", "sales_invoices_sales_invoices", "payments_payments"],
        "metrics": ["outstanding balance", "total paid", "regional average outstanding"], "filters": [],
        "time_range": None, "group_by": ["customer"], "ranking": None,
        "joins": [
            {"left": "sales_invoices_sales_invoices.customer_id", "right": "customers_customers.customer_id"},
            {"left": "payments_payments.invoice_id", "right": "sales_invoices_sales_invoices.invoice_id"},
        ],
        "assumptions": [], "needs_clarification": False, "clarification_question": None,
    }), schema=SCHEMA, original_question=Q2)
    assert plan_constraint_feedback(plan, SQL2) == []


def test_one_query_cannot_satisfy_both_questions_run_together():
    # Why the combined message failed: the checks for the receivables question
    # reject the expenses SQL. The fix is to split the questions, not relax the checks.
    assert local_semantic_feedback(Q1 + Q2, SQL1, SCHEMA)
