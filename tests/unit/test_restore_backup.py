"""Offline recovery: real auth SQL, uploaded SQLite, Chroma and cold process."""

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import pytest
from backend.backups import BackupSafetyError, create_snapshot, restore_snapshot
from backend.maintenance import database_lease

WRITER = r"""
import sys, sqlite3
from pathlib import Path
root=Path(sys.argv[1]); (root/'uploads'/'nested').mkdir(parents=True)
from apps.core import local_state
local_state.STATE_DIRECTORY=root/'state';local_state.STATE_PATH=root/'state'/'state.json'
from backend import database
from backend.models import User
from backend.workspace_repository import WorkspaceRepository
database.configure_database('sqlite:///'+str(root/'auth.db'));database.init_db()
source=root/'uploads'/'nested'/'dataset.sqlite'
with sqlite3.connect(source) as db:
 db.execute('CREATE TABLE sales(amount INTEGER)');db.executemany('INSERT INTO sales VALUES (?)',[(12,),(30,)])
with database.SessionLocal() as db:
 for owner in ['owner-a','owner-b']:
  db.add(User(id=owner,full_name='Synthetic',email=owner+'@example.test',password_hash='synthetic-hash',workspace_type='personal',workspace_role='owner'))
 db.commit();repo=WorkspaceRepository(db)
 for owner,ws in [('owner-a','a'),('owner-b','b')]:
  repo.ensure_tenant(owner,owner,name='Synthetic',workspace_type='personal')
  repo.save_workspace({'id':ws,'name':ws,'owner_user_id':owner,'database_uri':'sqlite:///'+str(source)},owner)
 db.commit()
from apps.api.session import SessionManager
from apps.core.chat_memory import ApprovedConversationMemory
manager=SessionManager();manager.hydrate_from_database();memory=ApprovedConversationMemory(root/'chroma')
for owner,ws,record_id in [('owner-a','a','keep'),('owner-a','a','deleted'),('owner-b','b','deleted')]:
 record=manager.append_history(ws,{'id':record_id,'question':'Synthetic sales '+record_id,'rows':[{'amount':42}],'columns':['amount'],'presentation':{'headline':'Saved localized headline'}})
 memory.save_approved_conversation(tenant_id=owner,workspace_id=ws,actor_user_id=owner,record=record)
manager.delete_history('owner-a','a','deleted') # Leave the physical stale vector deliberately.
manager.add_workspace({'id':'remote','owner_user_id':'owner-a','source_type':'server','database_uri':'postgresql://test:LOCAL_ONLY_DB_PASSWORD@db.invalid/db','connect_args':{'password':'LOCAL_ONLY_DB_PASSWORD'}})
(root/'uploads'/'credentials.txt').write_text('LOCAL_ONLY_DB_PASSWORD')
"""

READER = r"""
import sys,sqlite3
from pathlib import Path
root=Path(sys.argv[1])
import os
os.environ["PUCHOO_UPLOAD_DIRECTORY"]=str(root/"datasets")
from apps.core import local_state
local_state.STATE_DIRECTORY=root/'state';local_state.STATE_PATH=root/'state'/'state.json'
local_state.STATE_DIRECTORY.mkdir();local_state.STATE_PATH.write_text('{"query_history":{"a":[{"id":"deleted"}]}}')
from backend import database
database.configure_database('sqlite:///'+str(root/'auth.db'))
from apps.api.session import SessionManager
from apps.core.chat_memory import ApprovedConversationMemory,GuardedConversationMemory
manager=SessionManager();manager.hydrate_from_database()
assert [r['id'] for r in manager.get_history('a')]==['keep']
assert manager.get_history('a')[0]['presentation']['headline']=='Saved localized headline'
workspace=manager.get_workspace('a');assert str(root/'datasets') in workspace['source_ref']
with sqlite3.connect(workspace['source_ref']) as db:assert db.execute('SELECT SUM(amount) FROM sales').fetchone()==(42,)
with sqlite3.connect(root/'auth.db') as db:assert db.execute('SELECT COUNT(*) FROM users').fetchone()==(2,)
assert 'database_uri' not in manager.get_workspace('remote')
memory=GuardedConversationMemory(ApprovedConversationMemory(root/'chroma'))
assert {r['id'] for r in memory.search_approved_conversations(tenant_id='owner-a',workspace_id='a',query='sales',limit=10)}=={'keep'}
assert {r['id'] for r in memory.search_approved_conversations(tenant_id='owner-b',workspace_id='b',query='sales',limit=10)}=={'deleted'}
from apps.core.workspaces import create_tabular_workspace
new=create_tabular_workspace('new','new.csv',b'amount\n7\n')
assert str(root/'datasets') in new.database_uri
manager.add_workspace({**new.as_dict(),'owner_user_id':'owner-a'})
"""


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    root = tmp_path_factory.mktemp("offline-snapshot")
    source = root / "source"
    subprocess.run([sys.executable, "-c", WRITER, str(source)], check=True)
    dest = root / "backups" / "2026-11-07"
    create_snapshot(
        source / "auth.db",
        source / "chroma",
        source / "uploads",
        dest,
        writers_stopped=True,
    )
    return source, dest


def test_clean_machine_roundtrip_keeps_datasets_accounts_deletion_policy_and_scopes(
    snapshot, tmp_path
):
    source, backup = snapshot
    result = restore_snapshot(
        backup, tmp_path / "clean-machine", acknowledge_privacy_review=True
    )
    # The reader must not be able to rely on the original absolute upload path.
    hidden = source.with_name("source-unavailable")
    source.rename(hidden)
    try:
        subprocess.run(
            [sys.executable, "-c", READER, str(tmp_path / "clean-machine")], check=True
        )
    finally:
        hidden.rename(source)
    assert result["database"].is_file()
    assert (
        len(
            set(json.loads((backup / "manifest.json").read_text())["datasets"].values())
        )
        == 1
    )  # Shared source deduplicated.
    assert not any(
        b"LOCAL_ONLY_DB_PASSWORD" in p.read_bytes()
        for p in backup.rglob("*")
        if p.is_file()
    )


def test_privacy_review_required_even_for_a_valid_old_snapshot(snapshot, tmp_path):
    with pytest.raises(BackupSafetyError, match="privacy"):
        restore_snapshot(snapshot[1], tmp_path / "unreviewed")
    assert not (tmp_path / "unreviewed").exists()


def test_restore_never_overwrites_existing_data(snapshot, tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep").write_text("important")
    with pytest.raises(BackupSafetyError, match="must not exist"):
        restore_snapshot(snapshot[1], destination, acknowledge_privacy_review=True)
    assert (destination / "keep").read_text() == "important"


@pytest.mark.parametrize(
    "corruption", ["hash", "traversal", "missing_dataset", "symlink", "legacy"]
)
def test_invalid_snapshots_fail_before_restore_publication(
    snapshot, tmp_path, corruption
):
    source = tmp_path / "bad"
    shutil.copytree(snapshot[1], source)
    manifest = json.loads((source / "manifest.json").read_text())
    if corruption == "hash":
        (source / "auth.db").write_bytes(b"not sqlite")
    elif corruption == "traversal":
        manifest["files"]["../outside"] = "bad"
    elif corruption == "missing_dataset":
        manifest["datasets"] = {}
    elif corruption == "symlink":
        (source / "link").symlink_to(source / "auth.db")
    else:
        (source / "manifest.json").unlink()
    if corruption != "legacy":
        (source / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(BackupSafetyError):
        restore_snapshot(source, tmp_path / "output", acknowledge_privacy_review=True)
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".puchoo-restore-*"))


def test_active_api_lease_blocks_snapshot_without_partial_publish(snapshot, tmp_path):
    source, _ = snapshot
    with database_lease(source / "auth.db", shared=True):
        with pytest.raises(RuntimeError, match="in use"):
            create_snapshot(
                source / "auth.db",
                source / "chroma",
                source / "uploads",
                tmp_path / "active",
                writers_stopped=True,
            )
    assert not (tmp_path / "active").exists()
    assert not list(tmp_path.glob(".puchoo-backup-*"))


def test_backup_requires_stopped_writer_acknowledgement(snapshot, tmp_path):
    source, _ = snapshot
    with pytest.raises(BackupSafetyError, match="ALL writers"):
        create_snapshot(
            source / "auth.db",
            source / "chroma",
            source / "uploads",
            tmp_path / "no-ack",
        )


def test_restore_failure_cleans_only_its_staging_directory(
    snapshot, tmp_path, monkeypatch
):
    import backend.backups as module

    def fail(*args):
        raise OSError("synthetic publish failure")

    monkeypatch.setattr(module, "_publish", fail)
    with pytest.raises(OSError):
        restore_snapshot(
            snapshot[1], tmp_path / "failed", acknowledge_privacy_review=True
        )
    assert not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".puchoo-restore-*"))


def test_newest_corrupt_snapshot_does_not_silently_restore_older(snapshot, tmp_path):
    from scripts.restore_latest_backup import restore_latest_backup

    backups = tmp_path / "backups"
    shutil.copytree(snapshot[1], backups / "2026-01")
    shutil.copytree(snapshot[1], backups / "2026-02")
    (backups / "2026-02" / "auth.db").write_bytes(b"broken")
    with pytest.raises(BackupSafetyError):
        restore_latest_backup(
            backups, tmp_path / "result", acknowledge_privacy_review=True
        )
    assert not (tmp_path / "result").exists()


def test_restore_publish_race_does_not_replace_new_existing_directory(
    snapshot, tmp_path, monkeypatch
):
    import backend.backups as module

    original = module._manifest
    destination = tmp_path / "raced"

    def validate(source):
        result = original(source)
        if source.name.startswith(".puchoo-restore-"):
            destination.mkdir()
            (destination / "important").write_text("keep")
        return result

    monkeypatch.setattr(module, "_manifest", validate)
    with pytest.raises(FileExistsError):
        restore_snapshot(snapshot[1], destination, acknowledge_privacy_review=True)
    assert (destination / "important").read_text() == "keep"


@pytest.mark.parametrize("reference", ["missing", "outside"])
def test_backup_rejects_missing_or_outside_dataset_without_partial_publish(
    snapshot, tmp_path, reference
):
    source, _ = snapshot
    auth = tmp_path / "auth.db"
    shutil.copy2(source / "auth.db", auth)
    outside = tmp_path / "other.db"
    with sqlite3.connect(outside) as db:
        db.execute("CREATE TABLE data(x)")
    with sqlite3.connect(auth) as db:
        db.execute(
            "UPDATE workspace_records SET source_ref=? WHERE id=?",
            (str(outside if reference == "outside" else tmp_path / "missing.db"), "a"),
        )
    with pytest.raises((BackupSafetyError, FileNotFoundError)):
        create_snapshot(
            auth,
            source / "chroma",
            source / "uploads",
            tmp_path / "bad-source",
            writers_stopped=True,
        )
    assert not (tmp_path / "bad-source").exists()
    assert not list(tmp_path.glob(".puchoo-backup-*"))
