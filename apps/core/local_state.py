"""Small local persistence layer for desktop Streamlit workspaces.

This is intentionally not a multi-user database. It keeps locally imported
workspaces and their audit trail available after a browser refresh. Server
passwords are never written to disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIRECTORY = PROJECT_ROOT / ".pucho"
STATE_PATH = STATE_DIRECTORY / "state.json"


def load_local_state() -> dict[str, Any]:
    """Load previously saved non-secret state, returning safe empty defaults."""

    default = {"workspaces": {}, "active_workspace_id": None, "workspace_guardrails": {}, "query_history": {}, "profile": {}}
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(raw, dict):
        return default
    for key in ("workspaces", "workspace_guardrails", "query_history", "profile"):
        if isinstance(raw.get(key), dict):
            default[key] = raw[key]
    if isinstance(raw.get("active_workspace_id"), str) or raw.get("active_workspace_id") is None:
        default["active_workspace_id"] = raw.get("active_workspace_id")
    return default


def save_local_state(
    *,
    workspaces: dict[str, dict[str, Any]],
    active_workspace_id: str | None,
    workspace_guardrails: dict[str, dict[str, Any]],
    query_history: dict[str, list[dict[str, Any]]],
    profile: dict[str, Any],
) -> None:
    """Persist only local source metadata and user-approved query history.

    A database-server URI embeds a password, so server sources are purposely
    excluded. Users reconnect those sources after a browser refresh.
    """

    local_workspaces = {
        workspace_id: workspace
        for workspace_id, workspace in workspaces.items()
        if workspace.get("source_type", "file") != "server"
    }
    local_ids = set(local_workspaces)
    state = {
        "workspaces": local_workspaces,
        "active_workspace_id": active_workspace_id if active_workspace_id in local_ids else next(iter(local_ids), None),
        "workspace_guardrails": {key: value for key, value in workspace_guardrails.items() if key in local_ids},
        "query_history": {key: value for key, value in query_history.items() if key in local_ids},
        "profile": profile,
    }
    STATE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary_path = STATE_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")
    temporary_path.replace(STATE_PATH)
