"""Tenant-scoped persistence for workspace metadata, controls, and history."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.core.local_state import load_local_state
from backend.models import (
    Tenant,
    TenantMembership,
    User,
    WorkspaceGuardrail,
    WorkspaceHistoryRecord,
    WorkspaceRecord,
)


SAFE_METADATA_KEYS = {"dialect", "tables", "row_count", "columns", "description"}


def _local_source_ref(workspace: dict[str, Any]) -> str | None:
    """Return a durable local path without persisting any server credentials."""

    if workspace.get("source_type") == "server":
        return None
    source_ref = workspace.get("source_ref")
    if source_ref:
        return str(Path(str(source_ref)).expanduser().resolve())
    database_uri = str(workspace.get("database_uri") or "")
    if database_uri.startswith("sqlite:///"):
        return str(Path(database_uri.removeprefix("sqlite:///")).expanduser().resolve())
    return None


@dataclass(frozen=True)
class LegacyImportResult:
    tenants_created: int = 0
    memberships_created: int = 0
    workspaces_imported: int = 0


class WorkspaceRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_tenant(self, tenant_id: str, owner_user_id: str, *, name: str, workspace_type: str) -> Tenant:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            tenant = Tenant(id=tenant_id, owner_user_id=owner_user_id, name=name, workspace_type=workspace_type)
            self.db.add(tenant)
            self.db.flush()
        return tenant

    def list_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        records = self.db.scalars(
            select(WorkspaceRecord).where(WorkspaceRecord.tenant_id == tenant_id).order_by(WorkspaceRecord.created_at)
        ).all()
        return [self._as_dict(record) for record in records]

    def get_for_tenant(self, workspace_id: str, tenant_id: str) -> dict[str, Any] | None:
        record = self.db.scalar(
            select(WorkspaceRecord).where(
                WorkspaceRecord.id == workspace_id,
                WorkspaceRecord.tenant_id == tenant_id,
            )
        )
        return self._as_dict(record) if record else None

    def save_workspace(self, workspace: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        record = self.db.get(WorkspaceRecord, str(workspace["id"]))
        if record is not None and record.tenant_id != tenant_id:
            raise ValueError("Workspace ID already belongs to another tenant")
        source_type = str(workspace.get("source_type", "file"))
        source_ref = _local_source_ref(workspace)
        availability = str(workspace.get("availability", "available"))
        if source_type == "server":
            source_ref = None
            availability = "unavailable"
        metadata = {key: workspace[key] for key in SAFE_METADATA_KEYS if key in workspace}
        if record is None:
            record = WorkspaceRecord(
                id=str(workspace["id"]), tenant_id=tenant_id, name=str(workspace.get("name") or "Workspace")
            )
            self.db.add(record)
        record.name = str(workspace.get("name") or record.name)
        record.source_type = source_type
        record.source_ref = str(source_ref) if source_ref is not None else None
        record.availability = availability
        record.metadata_json = json.dumps(metadata, default=str)
        self.db.flush()
        return self._as_dict(record)

    def save_guardrails(self, workspace_id: str, settings: dict[str, Any]) -> None:
        record = self.db.get(WorkspaceGuardrail, workspace_id)
        if record is None:
            record = WorkspaceGuardrail(workspace_id=workspace_id)
            self.db.add(record)
        record.settings_json = json.dumps(settings)
        self.db.flush()

    def get_guardrails(self, workspace_id: str) -> dict[str, Any]:
        record = self.db.get(WorkspaceGuardrail, workspace_id)
        return json.loads(record.settings_json) if record else {}

    def save_history(self, workspace_id: str, records: list[dict[str, Any]]) -> None:
        existing = self.db.scalars(
            select(WorkspaceHistoryRecord).where(WorkspaceHistoryRecord.workspace_id == workspace_id)
        ).all()
        for record in existing:
            self.db.delete(record)
        for position, payload in enumerate(records):
            self.db.add(WorkspaceHistoryRecord(
                id=str(payload.get("id") or f"{workspace_id}-{position}"),
                workspace_id=workspace_id,
                position=position,
                payload_json=json.dumps(payload, default=str),
            ))
        self.db.flush()

    def get_history(self, workspace_id: str) -> list[dict[str, Any]]:
        records = self.db.scalars(
            select(WorkspaceHistoryRecord)
            .where(WorkspaceHistoryRecord.workspace_id == workspace_id)
            .order_by(WorkspaceHistoryRecord.position)
        ).all()
        return [json.loads(record.payload_json) for record in records]

    @staticmethod
    def _as_dict(record: WorkspaceRecord) -> dict[str, Any]:
        workspace = {
            "id": record.id,
            "name": record.name,
            "owner_user_id": record.tenant_id,
            "tenant_id": record.tenant_id,
            "source_type": record.source_type,
            "source_ref": record.source_ref,
            "availability": record.availability,
            **json.loads(record.metadata_json or "{}"),
        }
        if record.source_type != "server" and record.source_ref:
            source_path = Path(record.source_ref).expanduser().resolve()
            if source_path.is_file():
                workspace["source_ref"] = str(source_path)
                workspace["database_uri"] = f"sqlite:///{source_path}"
                workspace["availability"] = "available"
            else:
                workspace["availability"] = "unavailable"
        return workspace


def import_legacy_local_state(db: Session, state: dict[str, Any] | None = None) -> LegacyImportResult:
    state = state or load_local_state()
    tenants_created = memberships_created = workspaces_imported = 0
    repository = WorkspaceRepository(db)
    users = db.scalars(select(User)).all()
    for user in users:
        tenant_id = user.workspace_owner_id or user.institute_owner_id or user.id
        owner = db.get(User, tenant_id) or user
        if db.get(Tenant, tenant_id) is None:
            repository.ensure_tenant(
                tenant_id,
                owner.id,
                name=owner.workspace_name or owner.institute_name or "Workspace",
                workspace_type=owner.workspace_type,
            )
            tenants_created += 1
        membership = db.scalar(select(TenantMembership).where(TenantMembership.user_id == user.id))
        if membership is None:
            role = "owner" if user.id == tenant_id else (user.workspace_role or "viewer")
            db.add(TenantMembership(tenant_id=tenant_id, user_id=user.id, role=role))
            memberships_created += 1
    db.flush()
    for workspace in state.get("workspaces", {}).values():
        workspace_id = str(workspace.get("id") or "")
        tenant_id = str(workspace.get("owner_user_id") or "")
        if not workspace_id or not tenant_id or db.get(Tenant, tenant_id) is None:
            continue
        if db.get(WorkspaceRecord, workspace_id) is None:
            repository.save_workspace(workspace, tenant_id)
            repository.save_guardrails(workspace_id, state.get("workspace_guardrails", {}).get(workspace_id, {}))
            repository.save_history(workspace_id, state.get("query_history", {}).get(workspace_id, []))
            workspaces_imported += 1
    return LegacyImportResult(tenants_created, memberships_created, workspaces_imported)
