"""Tests for deterministic intent planning and focused schema retrieval."""

from __future__ import annotations

import unittest

from apps.core.semantic_layer import (
    build_query_plan,
    plan_semantic_feedback,
    render_planned_question,
    select_relevant_schema,
)


BUSINESS_SCHEMA = """Table: customers
Columns: customer_id (INTEGER), customer_name (TEXT), status (TEXT)

Table: invoices
Columns: invoice_id (INTEGER), customer_id (INTEGER), total_amount (INTEGER), payment_status (TEXT), invoice_date (TEXT)

Table: payments
Columns: payment_id (INTEGER), invoice_id (INTEGER), amount_paid (INTEGER)

Table: products
Columns: product_id (INTEGER), product_name (TEXT), category (TEXT)

Table: invoice_items
Columns: invoice_item_id (INTEGER), invoice_id (INTEGER), product_id (INTEGER), quantity (INTEGER), discount_amount (INTEGER), line_total (INTEGER)

Table: employees
Columns: employee_id (INTEGER), full_name (TEXT)"""


class SemanticLayerTests(unittest.TestCase):
    def test_builds_structured_receivables_plan(self) -> None:
        plan = build_query_plan(
            BUSINESS_SCHEMA,
            "Show top 10 customers by outstanding balance with unpaid invoice count, partial invoice count, total billed and total paid",
        )
        self.assertEqual(10, plan.limit)
        self.assertEqual("customer", plan.grain)
        self.assertIn("outstanding_balance", plan.metrics)
        self.assertIn("customers", plan.tables)
        self.assertIn("invoices", plan.tables)
        self.assertIn("payments", plan.tables)
        self.assertNotIn("invoice_count", plan.metrics)

    def test_focused_schema_excludes_unrelated_tables(self) -> None:
        plan = build_query_plan(BUSINESS_SCHEMA, "Show customers by outstanding balance and total paid")
        focused = select_relevant_schema(BUSINESS_SCHEMA, plan)
        self.assertIn("Table: customers", focused)
        self.assertIn("Table: invoices", focused)
        self.assertIn("Table: payments", focused)
        self.assertNotIn("Table: employees", focused)

    def test_plan_prompt_is_structured_and_authoritative(self) -> None:
        plan = build_query_plan(BUSINESS_SCHEMA, "Top 5 products by sales value")
        rendered = render_planned_question(plan)
        self.assertIn("Validated intent plan", rendered)
        self.assertIn('"limit":5', rendered)
        self.assertIn("sales_value", rendered)

    def test_explicit_ranking_metric_and_category_grain_are_preserved(self) -> None:
        plan = build_query_plan(
            BUSINESS_SCHEMA,
            "For each product category show sales value and average discount, then rank categories by sales value",
        )
        self.assertEqual("category", plan.grain)
        self.assertEqual("sales_value descending", plan.order_by)

    def test_plan_validator_rejects_unrelated_schema_table(self) -> None:
        plan = build_query_plan(BUSINESS_SCHEMA, "Show customers by outstanding balance")
        feedback = plan_semantic_feedback(
            plan,
            "SELECT c.customer_name FROM customers c JOIN employees e ON e.employee_id = c.customer_id",
        )
        self.assertTrue(any("employees" in item for item in feedback))

    def test_plan_validator_requires_all_requested_metric_aliases(self) -> None:
        plan = build_query_plan(BUSINESS_SCHEMA, "Show products with quantity sold and average discount")
        feedback = plan_semantic_feedback(
            plan,
            "SELECT p.product_name, SUM(i.quantity) AS total_quantity_sold FROM products p JOIN invoice_items i ON i.product_id=p.product_id GROUP BY p.product_name",
        )
        self.assertTrue(any("average_discount" in item for item in feedback))


if __name__ == "__main__":
    unittest.main()
