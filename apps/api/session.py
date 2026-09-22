"""In-process session store for development.

In production, this would be backed by Redis or a database.
"""

from typing import Any, Dict, List

class SessionManager:
    def __init__(self) -> None:
        self.workspaces: Dict[str, Dict[str, Any]] = {}
        self.workspace_guardrails: Dict[str, Dict[str, Any]] = {}
        self.query_history: Dict[str, List[Dict[str, Any]]] = {}
        self.profile: Dict[str, str] = {
            "name": "",
            "email": "",
            "department": "",
            "timezone": "UTC"
        }
        self.schema_snapshots: Dict[str, str] = {}
        # Stores active proposal per workspace to avoid stale references
        self.active_proposals: Dict[str, Dict[str, Any]] = {}

    def get_workspace(self, workspace_id: str) -> Dict[str, Any] | None:
        return self.workspaces.get(workspace_id)

    def add_workspace(self, workspace: Dict[str, Any]) -> None:
        ws_id = workspace["id"]
        self.workspaces[ws_id] = workspace
        self.workspace_guardrails.setdefault(ws_id, {
            "max_rows": 500,
            "timeout_seconds": 30,
            "confirm_complex_queries": False
        })
        self.query_history.setdefault(ws_id, [])

    def remove_workspace(self, workspace_id: str) -> None:
        self.workspaces.pop(workspace_id, None)
        self.workspace_guardrails.pop(workspace_id, None)
        self.query_history.pop(workspace_id, None)
        self.schema_snapshots.pop(f"schema_{workspace_id}", None)
        self.active_proposals.pop(workspace_id, None)

# Global singleton for the development server
session_manager = SessionManager()
