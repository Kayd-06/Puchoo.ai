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


def test_repository_restores_local_database_uri_after_restart(tmp_path):
    from backend.workspace_repository import WorkspaceRepository

    source = tmp_path / "business.db"
    source.touch()
    database.configure_database("sqlite:///" + (tmp_path / "repository.db").as_posix())
    database.init_db()
    sessions = sessionmaker(bind=database.engine, expire_on_commit=False)
    with sessions() as db:
        db.add(_user("owner"))
        db.commit()
        repository = WorkspaceRepository(db)
        repository.ensure_tenant("owner", "owner", name="Acme", workspace_type="business")
        repository.save_workspace(
            {
                "id": "business",
                "name": "My Business",
                "source_type": "spreadsheet_collection",
                "database_uri": f"sqlite:///{source}",
                "dialect": "sqlite",
            },
            "owner",
        )
        db.commit()

    with sessions() as db:
        restored = WorkspaceRepository(db).get_for_tenant("business", "owner")
        assert restored["source_ref"] == str(source)
        assert restored["database_uri"] == f"sqlite:///{source}"
        assert restored["availability"] == "available"


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


def _fresh(tmp_path, name="history.db"):
    database.configure_database("sqlite:///" + (tmp_path / name).as_posix())
    database.init_db()
    return sessionmaker(bind=database.engine, expire_on_commit=False)


def test_history_ids_only_need_to_be_unique_per_workspace(tmp_path):
    from backend.workspace_repository import WorkspaceRepository

    sessions = _fresh(tmp_path)
    with sessions() as db:
        db.add(_user("owner"))
        db.commit()
        repository = WorkspaceRepository(db)
        repository.ensure_tenant("owner", "owner", name="Acme", workspace_type="business")
        for ws in ("one", "two"):
            repository.save_workspace({"id": ws, "name": ws, "source_type": "file"}, "owner")
            repository.save_history(ws, [{"id": "same-id", "question": ws}])
        db.commit()
        assert repository.get_history("one")[0]["question"] == "one"
        assert repository.get_history("two")[0]["question"] == "two"


def test_history_save_appends_instead_of_rewriting_rows(tmp_path):
    from backend.models import WorkspaceHistoryRecord
    from backend.workspace_repository import WorkspaceRepository

    sessions = _fresh(tmp_path)
    with sessions() as db:
        db.add(_user("owner"))
        db.commit()
        repository = WorkspaceRepository(db)
        repository.ensure_tenant("owner", "owner", name="Acme", workspace_type="business")
        repository.save_workspace({"id": "ws", "name": "ws", "source_type": "file"}, "owner")
        repository.save_history("ws", [{"id": "q1"}, {"id": "q2"}])
        db.commit()
        before = {r.entry_id: r.id for r in db.query(WorkspaceHistoryRecord)}

        # Newest first, as the query router inserts at index 0.
        repository.save_history("ws", [{"id": "q3"}, {"id": "q1"}, {"id": "q2"}])
        db.commit()
        after = {r.entry_id: r.id for r in db.query(WorkspaceHistoryRecord)}
        assert after["q1"] == before["q1"] and after["q2"] == before["q2"]
        assert [item["id"] for item in repository.get_history("ws")] == ["q3", "q1", "q2"]

        repository.save_history("ws", [{"id": "q3"}, {"id": "q2"}])
        db.commit()
        assert [item["id"] for item in repository.get_history("ws")] == ["q3", "q2"]
        repository.save_history("ws", [])
        db.commit()
        assert repository.get_history("ws") == []


def test_session_save_only_writes_the_changed_workspace_and_survives_id_clash(tmp_path, monkeypatch):
    from apps.api.session import SessionManager
    from backend import workspace_repository
    from backend.workspace_repository import WorkspaceRepository

    sessions = _fresh(tmp_path, "session.db")
    with sessions() as db:
        db.add_all([_user("owner-a"), _user("owner-b")])
        db.commit()
        repository = WorkspaceRepository(db)
        repository.ensure_tenant("owner-b", "owner-b", name="B", workspace_type="business")
        repository.save_workspace({"id": "clash", "name": "B's", "source_type": "file"}, "owner-b")
        db.commit()

    monkeypatch.setattr("apps.api.session.save_local_state", lambda **_kwargs: None)
    manager = SessionManager.__new__(SessionManager)
    manager.workspaces = {
        "a1": {"id": "a1", "name": "A1", "owner_user_id": "owner-a", "source_type": "file"},
        "a2": {"id": "a2", "name": "A2", "owner_user_id": "owner-a", "source_type": "file"},
        "clash": {"id": "clash", "name": "Imposter", "owner_user_id": "owner-a", "source_type": "file"},
    }
    manager.workspace_guardrails = {}
    manager.query_history = {"a1": [{"id": "q1"}], "a2": [{"id": "q2"}], "clash": []}
    manager.profile = {}

    written: list[str] = []
    original = workspace_repository.WorkspaceRepository.save_workspace

    def spy(self, workspace, tenant_id):
        written.append(workspace["id"])
        return original(self, workspace, tenant_id)

    monkeypatch.setattr(workspace_repository.WorkspaceRepository, "save_workspace", spy)

    manager.save(active_workspace_id="a1")
    assert written == ["a1"]

    manager.save(active_workspace_id="clash")  # must not raise
    with sessions() as db:
        record = WorkspaceRepository(db).get_for_tenant("clash", "owner-b")
        assert record["name"] == "B's"
        assert WorkspaceRepository(db).get_for_tenant("a2", "owner-a") is None


def test_migration_0016_round_trip_keeps_history(tmp_path):
    from alembic import command
    from sqlalchemy import text

    _fresh(tmp_path, "migrate.db")
    with database.engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, full_name, email, password_hash, workspace_type, workspace_role, created_at) VALUES ('o','o','o@x.com','x','business','owner',CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO tenants (id, owner_user_id, name, workspace_type, created_at) VALUES ('o','o','A','business',CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO workspace_records (id, tenant_id, name, source_type, availability, metadata_json, created_at, updated_at) VALUES ('w','o','W','file','available','{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO workspace_history_records (id, workspace_id, entry_id, position, payload_json) VALUES ('u1','w','q1',0,'{\"id\": \"q1\"}')"))
    config = database._alembic_config()
    command.downgrade(config, "20261015_0015")
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM workspace_history_records")).scalars().all() == ["q1"]
    command.upgrade(config, "head")
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT entry_id FROM workspace_history_records")).scalars().all() == ["q1"]
