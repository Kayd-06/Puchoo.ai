"""Tests for durable local workspace state without server secrets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.core.local_state import load_local_state, save_local_state


class LocalStateTests(unittest.TestCase):
    def test_saves_local_workspace_and_history_but_excludes_server_uri(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory) / ".pucho"
            state_path = state_directory / "state.json"
            with patch("apps.core.local_state.STATE_DIRECTORY", state_directory), patch("apps.core.local_state.STATE_PATH", state_path):
                save_local_state(
                    workspaces={
                        "local": {"id": "local", "name": "Spreadsheet", "database_uri": "sqlite:////tmp/data.db", "source_type": "spreadsheet"},
                        "server": {"id": "server", "name": "Server", "database_uri": "postgresql+psycopg://readonly:secret@db.example.com/app", "source_type": "server"},
                    },
                    active_workspace_id="server",
                    workspace_guardrails={"local": {"max_rows": 100}, "server": {"max_rows": 100}},
                    query_history={"local": [{"question": "Actual local question"}], "server": [{"question": "Secret server question"}]},
                    profile={"name": "Local user"},
                )

                saved = load_local_state()

        self.assertEqual({"local"}, set(saved["workspaces"]))
        self.assertEqual("local", saved["active_workspace_id"])
        self.assertEqual({"local"}, set(saved["query_history"]))
