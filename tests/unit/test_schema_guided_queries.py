"""Tests for narrow, schema-inspected query routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

from apps.core.schema_guided_queries import build_schema_guided_query


class SchemaGuidedQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_uri = f"sqlite:///{Path(self.temp_dir.name) / 'business.db'}"
        engine = create_engine(self.database_uri)
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE products (product_id INTEGER, product_name TEXT, category TEXT)'))
            connection.execute(text('CREATE TABLE invoice_items (invoice_id INTEGER, product_id INTEGER, quantity INTEGER, line_total REAL)'))
            connection.execute(text('CREATE TABLE sales_invoices (invoice_id INTEGER, invoice_date TEXT)'))
            connection.execute(text('CREATE TABLE expenses (expense_date TEXT, expense_category TEXT, amount REAL)'))
            connection.execute(text("INSERT INTO products VALUES (1, 'A', 'Core'), (2, 'B', 'Office')"))
            connection.execute(text("INSERT INTO sales_invoices VALUES (1, '2026-01-01'), (2, '2026-02-01'), (3, '2023-09-20')"))
            connection.execute(text('INSERT INTO invoice_items VALUES (1, 1, 10, 100.0), (2, 2, 8, 250.0), (3, 1, 5, 50.0)'))
            connection.execute(text("INSERT INTO expenses VALUES ('2026-01-01', 'Travel', 100.50), ('2026-02-01', 'Travel', 99.50), ('2026-02-01', 'Software', 250.00)"))
        engine.dispose()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_plain_highest_sold_product_uses_quantity_and_period(self) -> None:
        sql = build_schema_guided_query(
            self.database_uri, "what was the highest sold product in last 2 years"
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("SUM(i.\"quantity\") AS units_sold", sql)
        self.assertIn("DATE('now', '-2 years')", sql)
        engine = create_engine(self.database_uri)
        with engine.connect() as connection:
            row = connection.execute(text(sql)).mappings().one()
        engine.dispose()
        self.assertEqual({"product_id": 1, "product_name": "A", "units_sold": 10}, dict(row))

    def test_explicit_sales_value_uses_line_total(self) -> None:
        sql = build_schema_guided_query(self.database_uri, "what product had the highest sales value")
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("SUM(i.\"line_total\") AS sales_value", sql)

    def test_lowest_sold_product_reverses_the_ranking_without_a_model(self) -> None:
        sql = build_schema_guided_query(
            self.database_uri,
            "Which product had the lowest total quantity sold in the last two years?",
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("ORDER BY units_sold ASC", sql)
        engine = create_engine(self.database_uri)
        with engine.connect() as connection:
            row = connection.execute(text(sql)).mappings().one()
        engine.dispose()
        self.assertEqual({"product_id": 2, "product_name": "B", "units_sold": 8}, dict(row))

    def test_unrelated_question_is_not_routed(self) -> None:
        self.assertIsNone(build_schema_guided_query(self.database_uri, "list all active customers"))

    def test_expenses_category_wise_uses_inspected_expense_table_and_period(self) -> None:
        sql = build_schema_guided_query(
            self.database_uri, "what was my expenses category wise in last 2 years"
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn('SUM(e."amount")', sql)
        self.assertIn("DATE('now', '-2 years')", sql)
        engine = create_engine(self.database_uri)
        with engine.connect() as connection:
            rows = connection.execute(text(sql)).mappings().all()
        engine.dispose()
        self.assertEqual(
            [
                {"expense_category": "Software", "total_expenses": 250.0},
                {"expense_category": "Travel", "total_expenses": 200.0},
            ],
            [dict(row) for row in rows],
        )

    def test_highest_expense_category_returns_one_row_and_tolerates_year_typo(self) -> None:
        sql = build_schema_guided_query(
            self.database_uri, "what were my highest expenses category wise in last three yeare"
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("DATE('now', '-3 years')", sql)
        self.assertIn("ORDER BY total_expenses DESC", sql)
        self.assertTrue(sql.endswith("LIMIT 1"))
        engine = create_engine(self.database_uri)
        with engine.connect() as connection:
            rows = connection.execute(text(sql)).mappings().all()
        engine.dispose()
        self.assertEqual([{"expense_category": "Software", "total_expenses": 250.0}], [dict(row) for row in rows])

    def test_product_category_sales_summary_uses_all_requested_metrics(self) -> None:
        sql = build_schema_guided_query(
            self.database_uri,
            "For each product category, show total quantity sold, total sales value, and average sales value per unit during the last 2 years. Order by total sales value descending.",
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn('SUM(i."quantity") AS total_quantity_sold', sql)
        self.assertIn('ROUND(SUM(i."line_total"), 2) AS total_sales_value', sql)
        self.assertIn('NULLIF(SUM(i."quantity"), 0)', sql)
        self.assertIn("DATE('now', '-2 years')", sql)
        self.assertTrue(sql.endswith("ORDER BY total_sales_value DESC"))
        engine = create_engine(self.database_uri)
        with engine.connect() as connection:
            rows = connection.execute(text(sql)).mappings().all()
        engine.dispose()
        self.assertEqual(
            [
                {"product_category": "Office", "total_quantity_sold": 8, "total_sales_value": 250.0, "average_sales_value_per_unit": 31.25},
                {"product_category": "Core", "total_quantity_sold": 10, "total_sales_value": 100.0, "average_sales_value_per_unit": 10.0},
            ],
            [dict(row) for row in rows],
        )

    def test_product_category_period_comparison_uses_adjacent_windows_and_percentage_change(self) -> None:
        sql = build_schema_guided_query(
            self.database_uri,
            "Compare total sales value by product category in the last two years versus the preceding two years. Show both periods and the percentage change.",
        )
        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("DATE('now', '-4 years')", sql)
        self.assertIn("DATE('now', '-2 years')", sql)
        self.assertIn("AS last_two_year_sales_value", sql)
        self.assertIn("AS preceding_two_year_sales_value", sql)
        self.assertIn("AS percentage_change", sql)
        engine = create_engine(self.database_uri)
        with engine.connect() as connection:
            rows = connection.execute(text(sql)).mappings().all()
        engine.dispose()
        self.assertEqual(
            [
                {"product_category": "Core", "last_two_year_sales_value": 100.0, "preceding_two_year_sales_value": 50.0, "percentage_change": 100.0},
                {"product_category": "Office", "last_two_year_sales_value": 250.0, "preceding_two_year_sales_value": 0.0, "percentage_change": None},
            ],
            [dict(row) for row in rows],
        )
