"""HTTP-level checks for upload limits, workspace file cleanup and SSE caps."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api.routers import notifications as notifications_router
from apps.api.session import session_manager
from apps.core import workspaces as workspace_core
from apps.core.workspaces import delete_workspace_files, workspace_source_file
from backend.config import settings
from backend.main import create_app
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload
from tests.unit.test_upload_limits import bomb_xlsx


def _signed_in(client, otp_codes, domain="hardening.com"):
    email = f"owner-{uuid4().hex}@{domain}"
    assert client.post("/api/v1/auth/signup", json=signup_payload(email=email), headers=csrf_headers(client)).status_code == 202
    finish_signup(client, email, otp_codes)
    return email


# --- Upload limits over HTTP ---------------------------------------------------

def test_upload_limits_return_clear_errors(tmp_path, monkeypatch, otp_codes):
    monkeypatch.setattr(workspace_core, "LOCAL_WORKSPACE_DIRECTORY", tmp_path)
    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)
    monkeypatch.setenv("UPLOAD_MAX_ROWS", "5")
    with TestClient(create_app(include_product=True)) as client:
        _signed_in(client, otp_codes)
        bomb = client.post(
            "/api/workspaces/upload",
            files={"file": ("bomb.xlsx", bomb_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=csrf_headers(client),
        )
        assert bomb.status_code == 413
        assert "compressed too heavily" in bomb.json()["detail"]

        rows = client.post(
            "/api/workspaces/upload",
            files={"file": ("rows.csv", b"a\n" + b"1\n" * 6, "text/csv")},
            headers=csrf_headers(client),
        )
        assert rows.status_code == 400
        assert rows.json()["detail"] == "rows.csv has more than 5 rows."

        multi = client.post(
            "/api/workspaces/upload-multiple",
            files=[("files", ("ok.csv", b"a\n1\n", "text/csv")), ("files", ("rows.csv", b"a\n" + b"1\n" * 6, "text/csv"))],
            headers=csrf_headers(client),
        )
        assert multi.status_code == 400
        assert "more than 5 rows" in multi.json()["detail"]
    # Rejected imports leave no half-written database behind.
    assert list(tmp_path.glob("*.db")) == []


# --- Workspace deletion removes stored files -----------------------------------

def test_workspace_source_file_only_accepts_files_inside_the_workspace_dir(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    inside = root / "pucho_import_x.db"
    inside.write_bytes(b"x")
    outside = tmp_path / "user.db"
    outside.write_bytes(b"x")
    assert workspace_source_file(f"sqlite:///{inside}", root=root) == inside.resolve()
    assert workspace_source_file(f"sqlite:///{outside}", root=root) is None
    assert workspace_source_file(f"sqlite:///{root}/../user.db", root=root) is None
    assert workspace_source_file(f"sqlite:///{root}", root=root) is None
    assert workspace_source_file("postgresql+psycopg://u:p@h/db", root=root) is None
    assert workspace_source_file("sqlite:///:memory:", root=root) is None
    assert workspace_source_file(None, root=root) is None
    link = root / "link.db"
    os.symlink(outside, link)
    assert workspace_source_file(f"sqlite:///{link}", root=root) is None
    assert delete_workspace_files(f"sqlite:///{link}", root=root) == []
    assert outside.exists()


def test_delete_workspace_files_removes_db_and_journals_and_ignores_missing(tmp_path):
    db = tmp_path / "pucho_source_a.db"
    sqlite3.connect(db).close()
    for suffix in ("-wal", "-shm"):
        (tmp_path / (db.name + suffix)).write_bytes(b"")
    removed = delete_workspace_files(f"sqlite:///{db}", root=tmp_path)
    assert {path.name for path in removed} == {db.name, db.name + "-wal", db.name + "-shm"}
    assert list(tmp_path.iterdir()) == []
    assert delete_workspace_files(f"sqlite:///{db}", root=tmp_path) == []


def test_deleting_a_workspace_removes_its_uploaded_file(tmp_path, monkeypatch, otp_codes):
    monkeypatch.setattr(workspace_core, "LOCAL_WORKSPACE_DIRECTORY", tmp_path)
    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)
    linked = tmp_path.parent / f"linked-{uuid4().hex}.db"
    sqlite3.connect(linked).execute("CREATE TABLE t (a INTEGER)").connection.close()
    with TestClient(create_app(include_product=True)) as client:
        _signed_in(client, otp_codes)
        uploaded = client.post(
            "/api/workspaces/upload",
            files={"file": ("sales.csv", b"a,b\n1,2\n", "text/csv")},
            headers=csrf_headers(client),
        )
        assert uploaded.status_code == 200
        workspace_id = uploaded.json()["id"]
        stored = workspace_source_file(session_manager.workspaces[workspace_id]["database_uri"], root=tmp_path)
        assert stored is not None and stored.exists()

        # A workspace pointing at a file outside the store keeps that file.
        outside_id = f"ws_{uuid4().hex[:12]}"
        owner_id = session_manager.workspaces[workspace_id]["owner_user_id"]
        session_manager.workspaces[outside_id] = {
            "id": outside_id, "name": "linked", "database_uri": f"sqlite:///{linked}",
            "dialect": "sqlite", "source_type": "sqlite", "owner_user_id": owner_id,
        }

        assert client.delete(f"/api/workspaces/{workspace_id}", headers=csrf_headers(client)).status_code in {200, 204}
        assert not stored.exists()
        assert client.delete(f"/api/workspaces/{outside_id}", headers=csrf_headers(client)).status_code in {200, 204}
        assert linked.exists()
    linked.unlink()


def test_shared_file_is_kept_until_the_last_workspace_using_it_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_core, "LOCAL_WORKSPACE_DIRECTORY", tmp_path)
    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)
    db = tmp_path / "pucho_shared.db"
    sqlite3.connect(db).close()
    uri = f"sqlite:///{db}"
    for workspace_id in ("ws_shared_a", "ws_shared_b"):
        session_manager.workspaces[workspace_id] = {"id": workspace_id, "database_uri": uri}
    session_manager.remove_workspace("ws_shared_a")
    assert db.exists()
    session_manager.remove_workspace("ws_shared_b")
    assert not db.exists()
    session_manager.remove_workspace("ws_shared_b")  # already gone: no error


# --- Notification stream cap ---------------------------------------------------

class _FakeRequest:
    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


def test_stream_slots_cap_and_release():
    slots = notifications_router.StreamSlots()
    assert all(slots.acquire("u", 3) for _ in range(3))
    assert not slots.acquire("u", 3)
    assert slots.acquire("other", 3)
    slots.release("u")
    assert slots.acquire("u", 3)
    for _ in range(5):
        slots.release("u")
    assert slots.count("u") == 0


def test_notification_streams_are_capped_per_user_and_released(app, monkeypatch):
    slots = notifications_router.StreamSlots()
    monkeypatch.setattr(notifications_router, "stream_slots", slots)
    monkeypatch.setattr(settings, "notification_streams_per_user", 3)
    monkeypatch.setattr(notifications_router, "STREAM_POLL_SECONDS", 0)
    user = SimpleNamespace(id=f"user-{uuid4().hex}")

    async def scenario():
        requests = [_FakeRequest() for _ in range(3)]
        responses = [await notifications_router.notification_stream(request, user) for request in requests]
        assert slots.count(user.id) == 3
        with pytest.raises(HTTPException) as caught:
            await notifications_router.notification_stream(_FakeRequest(), user)
        assert caught.value.status_code == 429
        assert slots.count(user.id) == 3

        # 1) The client disconnects: the stream ends and frees its slot.
        iterator = responses[0].body_iterator
        assert (await iterator.__anext__()).startswith(": keepalive")
        requests[0].disconnected = True
        with pytest.raises(StopAsyncIteration):
            while True:
                await iterator.__anext__()
        assert slots.count(user.id) == 2

        # 2) The server tears the stream down mid-flight (cancellation/close).
        iterator = responses[1].body_iterator
        await iterator.__anext__()
        await iterator.aclose()
        assert slots.count(user.id) == 1

        # 3) The response never started streaming; its background task releases.
        await responses[2].background()
        assert slots.count(user.id) == 0
        # Releasing twice never frees someone else's slot.
        await responses[2].background()
        await notifications_router.notification_stream(_FakeRequest(), user)
        await responses[0].background()
        assert slots.count(user.id) == 1

    asyncio.run(scenario())


def test_extra_stream_over_http_gets_429(app, otp_codes, monkeypatch):
    slots = notifications_router.StreamSlots()
    monkeypatch.setattr(notifications_router, "stream_slots", slots)
    with TestClient(create_app(include_product=True)) as client:
        _signed_in(client, otp_codes, domain="ssecap.com")
        me = client.get("/api/v1/auth/me")
        user_id = me.json().get("id") or me.json().get("user", {}).get("id")
        assert user_id
        for _ in range(settings.notification_streams_per_user):
            assert slots.acquire(user_id, settings.notification_streams_per_user)
        response = client.get("/api/notifications/stream")
        assert response.status_code == 429
        assert "Too many open notification streams" in response.json()["detail"]
