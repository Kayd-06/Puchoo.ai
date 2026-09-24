"""Small regression suite for representative complex analytics intents."""

from __future__ import annotations

import unittest

from apps.core.semantic_layer import build_query_plan, select_relevant_schema


SCHEMA = """Table: customers_customers
Columns: customer_id (INTEGER), customer_name (TEXT), status (TEXT)

Table: departments_departments
Columns: department_id (INTEGER), department_name (TEXT), monthly_budget (INTEGER)

Table: expenses_expenses
Columns: expense_id (INTEGER), department_id (INTEGER), expense_date (TEXT), amount (INTEGER), payment_status (TEXT)

Table: products_products
Columns: product_id (INTEGER), product_name (TEXT), category (TEXT), stock_quantity (INTEGER)

Table: invoice_items_invoice_items
Columns: invoice_item_id (INTEGER), invoice_id (INTEGER), product_id (INTEGER), quantity (INTEGER), discount_amount (INTEGER), line_total (INTEGER)

Table: sales_invoices_sales_invoices
Columns: invoice_id (INTEGER), customer_id (INTEGER), invoice_date (TEXT), total_amount (INTEGER), payment_status (TEXT)

Table: payments_payments
Columns: payment_id (INTEGER), invoice_id (INTEGER), amount_paid (INTEGER)

Table: employees_employees
Columns: employee_id (INTEGER), department_id (INTEGER), monthly_salary (INTEGER)"""


class QueryPlanningEvaluationTests(unittest.TestCase):
    CASES = (
        (
            "Top 10 customers by outstanding balance with unpaid invoice count, partial invoice count, total billed and total paid",
            {"outstanding_balance", "unpaid_invoice_count", "partial_invoice_count", "total_billed_amount", "total_paid_amount"},
            {"customers_customers", "sales_invoices_sales_invoices", "payments_payments"},
        ),
        (
            "For each product category show quantity sold, total sales value, average discount, and number of invoices",
            {"quantity_sold", "sales_value", "average_discount", "invoice_count"},
            {"products_products", "invoice_items_invoice_items"},
        ),
        (
            "Which departments spent above their monthly budget? Show total expenses and budget",
            {"expense_total", "budget"},
            {"departments_departments", "expenses_expenses"},
        ),
        (
            "Show invoice revenue over the rolling 90 days",
            {"revenue"},
            {"sales_invoices_sales_invoices"},
        ),
    )

    def test_representative_questions_produce_expected_intent(self) -> None:
        for question, metrics, tables in self.CASES:
            with self.subTest(question=question):
                plan = build_query_plan(SCHEMA, question)
                self.assertTrue(metrics <= set(plan.metrics))
                self.assertTrue(tables <= set(plan.tables))
                focused = select_relevant_schema(SCHEMA, plan)
                for table in tables:
                    self.assertIn(f"Table: {table}", focused)

    def test_rolling_window_is_structured(self) -> None:
        plan = build_query_plan(SCHEMA, "Show invoice revenue over the rolling 90 days")
        self.assertEqual("rolling 90 days ending today", plan.time_range)


if __name__ == "__main__":
    unittest.main()
