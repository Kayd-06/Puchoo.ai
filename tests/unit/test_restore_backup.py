"""Safety checks for local SQLite and Chroma backup restores."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest


def _restore_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "restore_latest_backup.py"
    spec = importlib.util.spec_from_file_location("restore_latest_backup", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _backup(directory: Path, name: str) -> Path:
    backup = directory / name
    (backup / "chroma").mkdir(parents=True)
    connection = sqlite3.connect(backup / "auth.db")
    connection.execute("create table users (id integer primary key, email text)")
    connection.execute("insert into users (email) values ('safe@example.com')")
    connection.commit()
    connection.close()
    (backup / "chroma" / "snapshot.txt").write_text("approved memory only", encoding="utf-8")
    return backup


def test_restore_uses_newest_complete_backup_and_keeps_sources_unchanged(tmp_path):
    module = _restore_module()
    backups = tmp_path / "backups"
    older = _backup(backups, "2026-10-01T00-00-00Z")
    newer = _backup(backups, "2026-10-02T00-00-00Z")
    destination_db = tmp_path / "restore" / "auth.db"
    destination_chroma = tmp_path / "restore" / "chroma"

    result = module.restore_latest_backup(backups, destination_db, destination_chroma)

    assert result["backup"] == newer
    assert destination_db.exists()
    assert (destination_chroma / "snapshot.txt").read_text(encoding="utf-8") == "approved memory only"
    assert sqlite3.connect(destination_db).execute("select email from users").fetchone() == ("safe@example.com",)
    assert (older / "auth.db").exists()


def test_restore_refuses_existing_or_production_like_destinations(tmp_path):
    module = _restore_module()
    backups = tmp_path / "backups"
    _backup(backups, "2026-10-02T00-00-00Z")
    existing = tmp_path / "existing.db"
    existing.write_text("do not replace", encoding="utf-8")

    with pytest.raises(module.RestoreSafetyError, match="must not exist"):
        module.restore_latest_backup(backups, existing, tmp_path / "new-chroma")
    with pytest.raises(module.RestoreSafetyError, match="production-like"):
        module.restore_latest_backup(backups, tmp_path / "puchoo_auth.db", tmp_path / "newer-chroma")
