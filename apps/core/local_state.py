"""Small local persistence layer for desktop Streamlit workspaces.

This is intentionally not a multi-user database. It keeps locally imported
workspaces and their audit trail available after a browser refresh. Server
passwords are never written to disk.
"""

from __future__ import annotations

import json
import os
import tempfile
from threading import RLock
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIRECTORY = PROJECT_ROOT / ".pucho"
STATE_PATH = STATE_DIRECTORY / "state.json"
# One API process owns snapshot capture, mutation and publication.
STATE_LOCK = RLock()


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


def _save_local_state(
    *,
    workspaces: dict[str, dict[str, Any]],
    active_workspace_id: str | None,
    workspace_guardrails: dict[str, dict[str, Any]],
    query_history: dict[str, list[dict[str, Any]]],
    profile: dict[str, Any],
) -> None:
    """Persist only local source metadata and user-approved query history.

    Server sources retain only non-secret identity metadata and are marked
    unavailable. Users reconnect credentials after a process restart.
    """

    # Server sources are represented durably by the tenant repository. Keep the
    # legacy desktop JSON strictly file-only so connection metadata and history
    # cannot leak into a second persistence store.
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
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=STATE_DIRECTORY,
                                         prefix=".state-", suffix=".tmp", delete=False) as handle:
            temporary_path = Path(handle.name)
            json.dump(state, handle, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(STATE_PATH)
        if os.name == "posix":
            descriptor = os.open(STATE_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def save_local_state(**kwargs) -> None:
    # Includes serialization, not just rename. API callers also mutate under this lock.
    with STATE_LOCK:
        _save_local_state(**kwargs)
