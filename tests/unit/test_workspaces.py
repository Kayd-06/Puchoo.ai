"""Tests for source onboarding without fabricated sample data."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from io import BytesIO
import tempfile
from pathlib import Path

import pandas as pd

from apps.core.workspaces import create_server_workspace, create_tabular_collection_workspace, create_tabular_workspace, get_schema_snapshot, get_schema_table_stats


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

    def test_multiple_csv_files_share_one_workspace(self) -> None:
        workspace = create_tabular_collection_workspace(
            "Sales collection",
            [
                ("customers.csv", b"customer_id,name\n1,Asha\n2,Kabir\n"),
                ("orders.csv", b"order_id,customer_id,total\n10,1,99\n11,2,42\n"),
            ],
            storage_dir=Path(self.temp_dir.name),
        )
        self.assertEqual("spreadsheet_collection", workspace.source_type)
        schema = get_schema_snapshot(workspace.database_uri)
        self.assertIn("Table: customers", schema)
        self.assertIn("Table: orders", schema)
        self.assertIn("customer_id: customers.customer_id, orders.customer_id", schema)

    def test_csv_sniffing_handles_utf8_multi_byte_boundaries(self) -> None:
        # 15 bytes of data + 2 byte char = 17 bytes, chunk size is 16
        # 'A' * 14 + ',' = 15 bytes. Next is 'ñ' which is 2 bytes (c3 b1).
        # Chunk 1 will end at 'c3' (invalid utf8).
        # The sniffer should decode with errors='replace' to avoid crashing.
        content = b'A' * 14 + b',\xc3\xb1\nB,C\n'
        workspace = create_tabular_workspace(
            "Boundary Test",
            "boundary.csv",
            content,
            storage_dir=Path(self.temp_dir.name),
        )
        self.assertEqual("spreadsheet", workspace.source_type)
        schema = get_schema_snapshot(workspace.database_uri)
        self.assertIn("Table: boundary", schema)


class ServerWorkspaceTests(unittest.TestCase):
    @patch("apps.core.workspaces.checked_connection_host", return_value="8.8.8.8")
    @patch("apps.core.workspaces.get_schema_snapshot", return_value="Table: events\nColumns: id (INTEGER)")
    def test_postgres_uri_is_built_from_discrete_connection_fields(self, schema_mock: object, _host_mock: object) -> None:
        password = "p@ss word"
        workspace = create_server_workspace(
            "Reporting",
            engine="postgresql",
            host="db.example.com",
            port=5432,
            database="reporting",
            username="readonly",
            password=password,
        )

        self.assertEqual("server", workspace.source_type)
        self.assertEqual("postgresql", workspace.dialect)
        self.assertEqual("postgresql+psycopg://readonly@8.8.8.8:5432/reporting", workspace.database_uri)
        self.assertNotIn("?", workspace.database_uri)
        self.assertNotIn(password, workspace.database_uri)
        self.assertNotIn(password, repr(workspace))
        self.assertEqual("require", workspace.connect_args["sslmode"])
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
            )
