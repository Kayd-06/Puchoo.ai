"""Tests for local, persistent ChromaDB schema retrieval."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from apps.core import vector_store


class VectorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_directory = vector_store.CHROMA_DIRECTORY
        self.root = Path(self.temp_dir.name)
        vector_store.CHROMA_DIRECTORY = self.root / "chroma"
        self.database = self.root / "workspace.sqlite"
        connection = sqlite3.connect(self.database)
        connection.execute("CREATE TABLE invoice_items (unit_price REAL, discount REAL, line_total REAL)")
        connection.commit()
        connection.close()

    def tearDown(self) -> None:
        vector_store.CHROMA_DIRECTORY = self.original_directory
        self.temp_dir.cleanup()

    def test_indexes_and_retrieves_schema_without_a_model_download(self) -> None:
        indexed = vector_store.index_workspace_schema("ws_vector_test", f"sqlite:///{self.database}")
        retrieved = vector_store.retrieve_workspace_schema("ws_vector_test", "unit price after discount")

        self.assertEqual(1, indexed)
        self.assertEqual(1, len(retrieved))
        self.assertIn("Table: invoice_items", retrieved[0])
        self.assertIn("unit_price", retrieved[0])
