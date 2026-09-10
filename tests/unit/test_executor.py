"""Tests for the one allowed database execution boundary."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from apps.core.executor import ReadOnlyExecutor
from apps.core.guardrails import SQLGuardrailError


class ReadOnlyExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "workspace.db"
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TABLE metrics (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
        connection.executemany("INSERT INTO metrics (amount) VALUES (?)", [(10,), (20,), (30,)])
        connection.commit()
        connection.close()
        self.executor = ReadOnlyExecutor(f"sqlite:///{self.path}", max_rows=2)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_executes_a_guarded_select_and_clamps_rows(self) -> None:
        result = self.executor.execute("SELECT id, amount FROM metrics ORDER BY id")
        self.assertEqual(2, result.row_count)
        self.assertEqual(["id", "amount"], result.columns)
        self.assertIn("LIMIT 2", result.sql)

    def test_rejects_write_sql_before_connecting_to_execution(self) -> None:
        with self.assertRaises(SQLGuardrailError):
            self.executor.execute("DELETE FROM metrics")
        connection = sqlite3.connect(self.path)
        self.assertEqual(3, connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0])
        connection.close()
