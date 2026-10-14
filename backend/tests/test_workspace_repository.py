"""Relational tenant workspace persistence and legacy import."""

from sqlalchemy.orm import sessionmaker

from backend import database
from backend.models import User


def _user(user_id: str, *, owner_id: str | None = None, role: str = "owner") -> User:
    return User(
        id=user_id,
        full_name=user_id,
        email=f"{user_id}@example.com",
        password_hash="unused",
        workspace_type="business",
        workspace_name="Acme",
        workspace_owner_id=owner_id,
        workspace_role=role,
    )


def test_repository_is_tenant_scoped_and_persists_guardrails_and_history(tmp_path):
    from backend.workspace_repository import WorkspaceRepository

    database.configure_database("sqlite:///" + (tmp_path / "repository.db").as_posix())
    database.init_db()
    sessions = sessionmaker(bind=database.engine, expire_on_commit=False)
    with sessions() as db:
        db.add_all([_user("owner-a"), _user("owner-b")])
        db.commit()
        repository = WorkspaceRepository(db)
        repository.ensure_tenant("tenant-a", "owner-a", name="Acme", workspace_type="business")
        repository.ensure_tenant("tenant-b", "owner-b", name="Other", workspace_type="business")
        repository.save_workspace(
            {"id": "sales", "name": "Sales", "source_type": "file", "source_ref": "sales.csv"},
            "tenant-a",
        )
        repository.save_guardrails("sales", {"max_rows": 25})
        repository.save_history("sales", [{"id": "q1", "question": "Revenue?"}])
        db.commit()

    with sessions() as db:
        repository = WorkspaceRepository(db)
        assert [item["id"] for item in repository.list_for_tenant("tenant-a")] == ["sales"]
        assert repository.list_for_tenant("tenant-b") == []
        assert repository.get_for_tenant("sales", "tenant-b") is None
        assert repository.get_guardrails("sales")["max_rows"] == 25
        assert repository.get_history("sales")[0]["id"] == "q1"


def test_legacy_import_backfills_memberships_once_and_hides_server_credentials(tmp_path):
    from backend.models import Tenant, TenantMembership, WorkspaceRecord
    from backend.workspace_repository import WorkspaceRepository, import_legacy_local_state

    database.configure_database("sqlite:///" + (tmp_path / "legacy.db").as_posix())
    database.init_db()
    sessions = sessionmaker(bind=database.engine, expire_on_commit=False)
    legacy = {
        "workspaces": {
            "server-ws": {
                "id": "server-ws",
                "name": "Warehouse",
                "owner_user_id": "owner",
                "source_type": "server",
                "database_uri": "postgresql://secret@database/private",
            }
        },
        "workspace_guardrails": {},
        "query_history": {},
        "profile": {},
    }
    with sessions() as db:
        db.add_all([_user("owner"), _user("editor", owner_id="owner", role="editor")])
        db.commit()
        first = import_legacy_local_state(db, legacy)
        second = import_legacy_local_state(db, legacy)
        db.commit()

        assert first.workspaces_imported == 1
        assert second.workspaces_imported == 0
        assert db.query(Tenant).count() == 1
        assert db.query(TenantMembership).count() == 2
        assert db.query(WorkspaceRecord).count() == 1
        workspace = WorkspaceRepository(db).get_for_tenant("server-ws", "owner")
        assert workspace["availability"] == "unavailable"
        assert "secret" not in repr(workspace)
        assert "database_uri" not in workspace
