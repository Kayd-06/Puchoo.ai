"""Single-process API cache: SQL is authoritative; JSON is a legacy/checkpoint store.

All production mutations enter serialized commands. This is not a multi-worker store.
"""

import logging
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
from typing import Any, Dict, Iterable, List

from apps.core.local_state import STATE_LOCK, load_local_state, save_local_state

logger = logging.getLogger(__name__)


def serialized(method):
    @wraps(method)
    def call(*args, **kwargs):
        with STATE_LOCK:
            return method(*args, **kwargs)
    return call


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

    @contextmanager
    def _edit(self, workspace_id=None, db_action=None):
        """Stage under one owner; restore cache on SQL failure, checkpoint after commit."""
        with STATE_LOCK:
            names = ("workspaces", "workspace_guardrails", "query_history", "profile", "active_proposals", "schema_snapshots")
            previous = {name: getattr(self, name) for name in names}
            # Runtime connection arguments may contain an SSLContext (not pickleable).
            self.workspaces = {key: dict(value) for key, value in self.workspaces.items()}
            for name in names[1:]:
                setattr(self, name, deepcopy(getattr(self, name)))
            try:
                yield
                self.save(active_workspace_id=workspace_id, db_action=db_action)
            except Exception:
                for name, value in previous.items():
                    setattr(self, name, value)
                raise

    @serialized
    def get_workspace(self, workspace_id):
        workspace = self.workspaces.get(workspace_id)
        return dict(workspace) if workspace else None

    @serialized
    def list_workspaces(self):
        return [dict(workspace) for workspace in self.workspaces.values()]

    @serialized
    def get_schema(self, workspace_id):
        return self.schema_snapshots.get(f"schema_{workspace_id}")

    @serialized
    def set_schema(self, workspace_id, schema):
        if workspace_id in self.workspaces:
            self.schema_snapshots[f"schema_{workspace_id}"] = schema

    @serialized
    def get_history(self, workspace_id):
        return deepcopy(self.query_history.get(workspace_id, []))

    def add_workspace(self, workspace):
        ws_id = workspace["id"]
        with self._edit(ws_id):
            if ws_id in self.workspaces:
                raise ValueError("Workspace already exists")
            self.workspaces[ws_id] = dict(workspace)
            self.workspace_guardrails[ws_id] = self.DEFAULT_GUARDRAILS.copy()
            self.query_history[ws_id] = []

    def append_history(self, workspace_id, record):
        from backend import database
        from backend.memory_deletions import generation, suppressed
        with self._edit(workspace_id):
            workspace = self.workspaces.get(workspace_id)
            if workspace is None:
                raise ValueError("Workspace was removed")
            tenant = workspace.get("owner_user_id")
            record = deepcopy(record)
            with database.SessionLocal() as db:
                record["memory_generation"] = generation(db, tenant, workspace_id)
                if suppressed(db, tenant, workspace_id, str(record.get("id")), record["memory_generation"]):
                    raise ValueError("History record was deleted")
            self.query_history.setdefault(workspace_id, []).insert(0, record)
        return record

    def set_guardrails(self, workspace_id, guardrails):
        with self._edit(workspace_id):
            if workspace_id not in self.workspaces:
                raise ValueError("Workspace was removed")
            self.workspace_guardrails[workspace_id] = dict(guardrails)

    def delete_history(self, tenant_id, workspace_id, record_id=None):
        from backend.memory_deletions import enqueue
        receipt = []
        def action(db):
            receipt.append(enqueue(db, tenant_id, workspace_id, record_id))
        with self._edit(workspace_id, action):
            workspace = self.workspaces.get(workspace_id)
            if not workspace or workspace.get("owner_user_id") != tenant_id:
                raise ValueError("Workspace not found")
            records = self.query_history.get(workspace_id, [])
            self.query_history[workspace_id] = [] if record_id is None else [row for row in records if str(row.get("id")) != record_id]
            self.active_proposals.pop(workspace_id, None)
        return receipt[0]

    def remove_workspace(self, workspace_id):
        from backend.models import WorkspaceRecord
        from backend.memory_deletions import enqueue
        removed = None
        def action(db):
            record = db.get(WorkspaceRecord, workspace_id)
            if record is not None:
                enqueue(db, record.tenant_id, workspace_id)
                db.delete(record)
        with self._edit(db_action=action):
            removed = self.workspaces.pop(workspace_id, None)
            self.workspace_guardrails.pop(workspace_id, None)
            self.query_history.pop(workspace_id, None)
            self.schema_snapshots.pop(f"schema_{workspace_id}", None)
            self.active_proposals.pop(workspace_id, None)
        uri = removed.get("database_uri") if isinstance(removed, dict) else None
        with STATE_LOCK:
            if uri and not any(ws.get("database_uri") == uri for ws in self.workspaces.values()):
                from apps.core.workspaces import delete_workspace_files
                delete_workspace_files(uri)

    @serialized
    def save(self, active_workspace_id=None, db_action=None):
        """SQL commits before the derived, best-effort JSON checkpoint."""
        if active_workspace_id is not None or db_action is not None:
            self._save_to_database([active_workspace_id] if active_workspace_id else [], db_action=db_action)
        try:
            save_local_state(workspaces=self.workspaces, active_workspace_id=active_workspace_id,
                workspace_guardrails=self.workspace_guardrails, query_history=self.query_history, profile=self.profile)
        except OSError:
            # SQL is durable. Stale JSON must never be replayed over it at startup.
            logger.warning("local_state_checkpoint_failed", exc_info=True)

    @serialized
    def hydrate_from_database(self):
        from sqlalchemy import select
        from backend import database
        from backend.models import WorkspaceRecord, Tenant, PersistenceMarker
        from backend.workspace_repository import WorkspaceRepository, import_legacy_local_state
        with database.SessionLocal() as db:
            if db.get(PersistenceMarker, "relational-authority-v1") is None:
                # Any existing tenant state is authoritative, including zero remaining workspaces.
                if db.scalar(select(Tenant.id).limit(1)) is None and db.scalar(select(WorkspaceRecord.id).limit(1)) is None:
                    import_legacy_local_state(db)
                db.add(PersistenceMarker(key="relational-authority-v1"))
                db.commit()
            repository = WorkspaceRepository(db)
            runtime = self.workspaces
            workspaces, guardrails, history = {}, {}, {}
            for record in db.scalars(select(WorkspaceRecord)).all():
                workspace = repository._as_dict(record)
                existing = runtime.get(record.id, {})
                if record.source_type == "server" and existing.get("owner_user_id") == record.tenant_id and existing.get("database_uri"):
                    for key in ("database_uri", "connect_args"):
                        if key in existing:
                            workspace[key] = existing[key]
                    workspace["availability"] = "available"
                workspaces[record.id] = workspace
                guardrails[record.id] = {**self.DEFAULT_GUARDRAILS, **repository.get_guardrails(record.id)}
                history[record.id] = repository.get_history(record.id)
            self.workspaces, self.workspace_guardrails, self.query_history = workspaces, guardrails, history

    def _save_to_database(self, workspace_ids: Iterable[str] | None = None, db_action=None) -> None:
        from backend import database
        from backend.models import Tenant, User
        from backend.workspace_repository import WorkspaceRepository

        ids = list(self.workspaces) if workspace_ids is None else list(workspace_ids)
        with database.SessionLocal() as db:
            repository = WorkspaceRepository(db)
            for workspace_id in ids:
                workspace = self.workspaces.get(workspace_id)
                if not workspace:
                    continue
                tenant_id = workspace.get("owner_user_id")
                if not tenant_id:
                    raise ValueError("Workspace requires a tenant owner")
                if db.get(Tenant, tenant_id) is None:
                    owner = db.get(User, tenant_id)
                    if owner is None:
                        raise ValueError("Workspace owner no longer exists")
                    repository.ensure_tenant(
                        tenant_id,
                        owner.id,
                        name=owner.workspace_name or owner.institute_name or "Workspace",
                        workspace_type=owner.workspace_type,
                    )
                repository.save_workspace(workspace, tenant_id)
                repository.save_guardrails(workspace_id, self.get_guardrails(workspace_id))
                repository.save_history(workspace_id, self.query_history.get(workspace_id, []))
            if db_action is not None:
                db_action(db)
            db.commit()

    @serialized
    def get_guardrails(self, workspace_id: str) -> Dict[str, Any]:
        """Return a complete guardrail configuration, including for legacy state."""

        return {
            **self.DEFAULT_GUARDRAILS,
            **self.workspace_guardrails.get(workspace_id, {}),
        }

# One singleton/owner per API process; run one API worker.
session_manager = SessionManager()
