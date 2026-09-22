"""In-process session store for development.

In production, this would be backed by Redis or a database.
"""

from typing import Any, Dict, List

from apps.core.local_state import load_local_state, save_local_state

class SessionManager:
    DEFAULT_GUARDRAILS = {
        "max_rows": 500,
        "timeout_seconds": 30,
        "confirm_complex_queries": False,
    }

    def __init__(self) -> None:
        saved = load_local_state()
        self.workspaces: Dict[str, Dict[str, Any]] = saved["workspaces"]
        self.workspace_guardrails: Dict[str, Dict[str, Any]] = {
            workspace_id: {**self.DEFAULT_GUARDRAILS, **guardrails}
            for workspace_id, guardrails in saved["workspace_guardrails"].items()
            if isinstance(guardrails, dict)
        }
        self.query_history: Dict[str, List[Dict[str, Any]]] = saved["query_history"]
        self.profile: Dict[str, str] = {
            "name": "",
            "email": "",
            "department": "",
            "timezone": "UTC",
            **saved["profile"],
        }
        self.schema_snapshots: Dict[str, str] = {}
        # Stores active proposal per workspace to avoid stale references
        self.active_proposals: Dict[str, Dict[str, Any]] = {}

    def get_workspace(self, workspace_id: str) -> Dict[str, Any] | None:
        return self.workspaces.get(workspace_id)

    def add_workspace(self, workspace: Dict[str, Any]) -> None:
        ws_id = workspace["id"]
        self.workspaces[ws_id] = workspace
        self.workspace_guardrails.setdefault(ws_id, self.DEFAULT_GUARDRAILS.copy())
        self.query_history.setdefault(ws_id, [])
        self.save(active_workspace_id=ws_id)

    def remove_workspace(self, workspace_id: str) -> None:
        self.workspaces.pop(workspace_id, None)
        self.workspace_guardrails.pop(workspace_id, None)
        self.query_history.pop(workspace_id, None)
        self.schema_snapshots.pop(f"schema_{workspace_id}", None)
        self.active_proposals.pop(workspace_id, None)
        self.save()

    def save(self, active_workspace_id: str | None = None) -> None:
        """Persist local workspaces without writing server credentials to disk."""

        save_local_state(
            workspaces=self.workspaces,
            active_workspace_id=active_workspace_id,
            workspace_guardrails=self.workspace_guardrails,
            query_history=self.query_history,
            profile=self.profile,
        )

    def get_guardrails(self, workspace_id: str) -> Dict[str, Any]:
        """Return a complete guardrail configuration, including for legacy state."""

        return {
            **self.DEFAULT_GUARDRAILS,
            **self.workspace_guardrails.get(workspace_id, {}),
        }

# Global singleton for the development server
session_manager = SessionManager()
