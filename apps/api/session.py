"""In-process session store for development.

In production, this would be backed by Redis or a database.
"""

import logging
from typing import Any, Dict, Iterable, List

from apps.core.local_state import load_local_state, save_local_state

logger = logging.getLogger(__name__)


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
        self._delete_from_database(workspace_id)
        self.save()

    def save(self, active_workspace_id: str | None = None) -> None:
        """Persist workspace state without writing server credentials to disk.

        Only the workspace that changed is written to the database. Without an
        ``active_workspace_id`` (e.g. after a removal, which deletes its own
        rows) only the local JSON snapshot is refreshed.
        """

        save_local_state(
            workspaces=self.workspaces,
            active_workspace_id=active_workspace_id,
            workspace_guardrails=self.workspace_guardrails,
            query_history=self.query_history,
            profile=self.profile,
        )
        if active_workspace_id is not None:
            self._save_to_database([active_workspace_id])

    def hydrate_from_database(self) -> None:
        """Import legacy JSON once, then make relational state authoritative."""

        from sqlalchemy import select

        from backend import database
        from backend.models import WorkspaceRecord
        from backend.workspace_repository import WorkspaceRepository, import_legacy_local_state

        # Capture compatible in-memory/local-state workspaces before the
        # relational records become authoritative.
        self._save_to_database()
        with database.SessionLocal() as db:
            import_legacy_local_state(db)
            db.commit()
            repository = WorkspaceRepository(db)
            persisted = db.scalars(select(WorkspaceRecord)).all()
            runtime = self.workspaces
            self.workspaces = {}
            for record in persisted:
                workspace = repository._as_dict(record)
                existing = runtime.get(record.id, {})
                if existing:
                    workspace.update(existing)
                if record.source_type == "server" and existing.get("database_uri"):
                    workspace["availability"] = "available"
                self.workspaces[record.id] = workspace
                self.workspace_guardrails[record.id] = {
                    **self.DEFAULT_GUARDRAILS,
                    **repository.get_guardrails(record.id),
                }
                self.query_history[record.id] = repository.get_history(record.id)

    def _save_to_database(self, workspace_ids: Iterable[str] | None = None) -> None:
        from sqlalchemy.exc import IntegrityError

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
                    continue
                try:
                    with db.begin_nested():
                        if db.get(Tenant, tenant_id) is None:
                            owner = db.get(User, tenant_id)
                            if owner is None:
                                continue
                            repository.ensure_tenant(
                                tenant_id,
                                owner.id,
                                name=owner.workspace_name or owner.institute_name or "Workspace",
                                workspace_type=owner.workspace_type,
                            )
                        repository.save_workspace(workspace, tenant_id)
                        repository.save_guardrails(workspace_id, self.get_guardrails(workspace_id))
                        repository.save_history(workspace_id, self.query_history.get(workspace_id, []))
                except ValueError:
                    # Workspace id already owned by another tenant: never
                    # overwrite it, and never fail the user's request.
                    logger.warning("skipping workspace persistence: id belongs to another tenant workspace=%s", workspace_id)
                except IntegrityError:
                    logger.warning("workspace persistence conflict; will retry on next save workspace=%s", workspace_id)
            db.commit()

    @staticmethod
    def _delete_from_database(workspace_id: str) -> None:
        from backend import database
        from backend.models import WorkspaceRecord

        with database.SessionLocal() as db:
            record = db.get(WorkspaceRecord, workspace_id)
            if record is not None:
                db.delete(record)
                db.commit()

    def get_guardrails(self, workspace_id: str) -> Dict[str, Any]:
        """Return a complete guardrail configuration, including for legacy state."""

        return {
            **self.DEFAULT_GUARDRAILS,
            **self.workspace_guardrails.get(workspace_id, {}),
        }

# Global singleton for the development server
session_manager = SessionManager()
