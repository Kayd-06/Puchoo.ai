"""Tests for source onboarding without fabricated sample data."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from io import BytesIO
import tempfile
from pathlib import Path

import pandas as pd

from apps.core.workspaces import (
    create_server_workspace,
    create_tabular_workspace,
    create_tabular_workspace_from_uploads,
    get_query_schema_context,
    get_schema_snapshot,
    get_schema_table_stats,
)


class TabularWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_csv_becomes_a_queryable_sqlite_workspace(self) -> None:
        workspace = create_tabular_workspace(
            "Actual uploaded data",
            "Quarterly Sales.csv",
            b"Product Name,Revenue\nAster,42\nNova,84\n",
            storage_dir=Path(self.temp_dir.name),
        )

        self.assertEqual("spreadsheet", workspace.source_type)
        self.assertEqual("sqlite", workspace.dialect)
        schema = get_schema_snapshot(workspace.database_uri)
        self.assertIn("Table: quarterly_sales", schema)
        self.assertIn("product_name", schema)
        self.assertIn("revenue", schema)

        table_stats = get_schema_table_stats(workspace.database_uri, include_row_counts=True)
        self.assertEqual([{"name": "quarterly_sales", "columns": 2, "rows": 2}], table_stats)

    def test_empty_csv_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_tabular_workspace("Empty", "empty.csv", b"", storage_dir=Path(self.temp_dir.name))

    def test_excel_sheets_become_separate_tables(self) -> None:
        workbook = BytesIO()
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            pd.DataFrame({"Month": ["January"], "Amount": [15]}).to_excel(writer, sheet_name="Monthly Sales", index=False)
            pd.DataFrame({"Region": ["North"]}).to_excel(writer, sheet_name="Regions", index=False)

        workspace = create_tabular_workspace("Workbook", "report.xlsx", workbook.getvalue(), storage_dir=Path(self.temp_dir.name))
        schema = get_schema_snapshot(workspace.database_uri)
        self.assertIn("Table: monthly_sales", schema)
        self.assertIn("Table: regions", schema)

    def test_collection_uploads_share_one_workspace_and_keep_file_names_in_table_names(self) -> None:
        workspace = create_tabular_workspace_from_uploads(
            "Retail inventory",
            [
                ("customers.csv", b"Customer,City\nAster,Delhi\n"),
                ("inventory.csv", b"SKU,Quantity\nP-100,12\n"),
            ],
            data_domain="business",
            storage_dir=Path(self.temp_dir.name),
        )

        self.assertEqual("spreadsheet_collection", workspace.source_type)
        self.assertEqual("business", workspace.data_domain)
        schema = get_schema_snapshot(workspace.database_uri)
        self.assertIn("Table: customers_customers", schema)
        self.assertIn("Table: inventory_inventory", schema)

    def test_business_and_education_collections_use_distinct_databases(self) -> None:
        business = create_tabular_workspace_from_uploads(
            "Retail inventory",
            [("stock.csv", b"SKU,Quantity\nP-100,12\n")],
            data_domain="business",
            storage_dir=Path(self.temp_dir.name),
        )
        education = create_tabular_workspace_from_uploads(
            "Class records",
            [("students.csv", b"Student,Grade\nAster,10\n")],
            data_domain="education",
            storage_dir=Path(self.temp_dir.name),
        )

        self.assertEqual("business", business.data_domain)
        self.assertEqual("education", education.data_domain)
        self.assertNotEqual(business.database_uri, education.database_uri)
        self.assertNotIn("students_students", get_schema_snapshot(business.database_uri))
        self.assertNotIn("stock_stock", get_schema_snapshot(education.database_uri))

    def test_collection_rejects_unknown_data_domain(self) -> None:
        with self.assertRaises(ValueError):
            create_tabular_workspace_from_uploads(
                "Mixed data",
                [("data.csv", b"Name\nAster\n")],
                data_domain="mixed",
                storage_dir=Path(self.temp_dir.name),
            )

    def test_query_context_adds_small_samples_from_relevant_tables(self) -> None:
        workspace = create_tabular_workspace_from_uploads(
            "Billing",
            [("invoice_items.csv", b"Unit Price,Discount,Line Total\n120,10,110\n")],
            data_domain="business",
            storage_dir=Path(self.temp_dir.name),
        )

        context = get_query_schema_context(
            workspace.database_uri,
            "Give me unit price and line total from invoice items",
        )
        self.assertIn("Table: invoice_items_invoice_items", context)
        self.assertIn("Example rows from invoice_items_invoice_items", context)
        self.assertIn("unit_price", context)

    def test_query_context_expands_to_related_join_tables(self) -> None:
        workspace = create_tabular_workspace_from_uploads(
            "Sales",
            [
                ("customers.csv", b"Customer ID,Customer Name\n1,Aster\n"),
                ("products.csv", b"Product ID,Category\n10,Home\n"),
                ("invoices.csv", b"Invoice ID,Customer ID,Invoice Date\n100,1,2026-01-01\n"),
                ("invoice_items.csv", b"Invoice ID,Product ID,Quantity\n100,10,2\n"),
                ("payments.csv", b"Invoice ID,Payment Method\n100,Card\n"),
            ],
            data_domain="business",
            storage_dir=Path(self.temp_dir.name),
        )
        context = get_query_schema_context(
            workspace.database_uri,
            "Which customers bought distinct product categories and used payment methods?",
        )
        self.assertIn("Table: customers_customers", context)
        self.assertIn("Table: products_products", context)
        self.assertIn("Table: invoice_items_invoice_items", context)
        self.assertIn("Table: payments_payments", context)


class ServerWorkspaceTests(unittest.TestCase):
    @patch("apps.core.workspaces.get_schema_snapshot", return_value="Table: events\nColumns: id (INTEGER)")
    def test_postgres_uri_is_built_from_discrete_connection_fields(self, schema_mock: object) -> None:
        workspace = create_server_workspace(
            "Reporting",
            engine="postgresql",
            host="db.example.com",
            port=5432,
            database="reporting",
            username="readonly",
            password="p@ss word",
            ssl_required=True,
        )

        self.assertEqual("server", workspace.source_type)
        self.assertEqual("postgresql", workspace.dialect)
        self.assertIn("postgresql+psycopg://readonly:p%40ss+word@db.example.com:5432/reporting", workspace.database_uri)
        self.assertTrue(workspace.database_uri.endswith("sslmode=require"))
        self.assertTrue(schema_mock.called)  # type: ignore[attr-defined]

    def test_server_rejects_invalid_host_before_connecting(self) -> None:
        with self.assertRaises(ValueError):
            create_server_workspace(
                "Reporting",
                engine="mysql",
                host="db.example.com/path",
                port=3306,
                database="reporting",
                username="readonly",
                password="secret",
                ssl_required=True,
            )
