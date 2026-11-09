"""Versioned offline SQLite + uploaded datasets + scoped Chroma snapshots.

Only fresh-directory restore is supported. No configuration, runtime connection
credentials, legacy JSON checkpoints or arbitrary directory trees are captured.
"""

from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from backend.maintenance import database_lease


class BackupSafetyError(RuntimeError):
    pass


def _publish(stage, destination):
    # Reserve the name exclusively: plain POSIX rename could replace somebody
    # else's newly-created empty directory after our initial preflight.
    destination.mkdir(mode=0o700)
    identity = destination.stat().st_ino
    try:
        os.rename(stage, destination)
    except BaseException:
        if destination.is_dir() and destination.stat().st_ino == identity:
            try:
                destination.rmdir()  # Never recursively delete an existing target.
            except OSError:
                pass
        raise


def _connection(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def _integrity(path):
    with closing(_connection(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise BackupSafetyError("SQLite integrity check failed")


def _sqlite_copy(source, target):
    with closing(_connection(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    os.chmod(target, 0o600)
    _integrity(target)


def _files(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise BackupSafetyError(
                "Symlinks and special files are not supported in snapshots"
            )
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[path.relative_to(root).as_posix()] = digest.hexdigest()
    return result


def _authority(db):
    try:
        if (
            db.execute(
                "SELECT 1 FROM persistence_markers WHERE key=?",
                ("relational-authority-v1",),
            ).fetchone()
            is None
        ):
            raise BackupSafetyError(
                "Relational authority marker is missing; legacy import needs manual review"
            )
        # These must be captured together, including empty tombstone tables.
        for table in (
            "memory_generations",
            "memory_deletions",
            "workspace_history_records",
        ):
            db.execute("SELECT 1 FROM " + table + " LIMIT 1")
    except sqlite3.DatabaseError as exc:
        raise BackupSafetyError(
            "Backup lacks required durable state/deletion schema"
        ) from exc


def create_snapshot(database, chroma, uploads, destination, *, writers_stopped=False):
    if not writers_stopped:
        raise BackupSafetyError(
            "Offline backup requires confirmation that ALL writers are stopped"
        )
    database, chroma, uploads, destination = map(
        Path, (database, chroma, uploads, destination)
    )
    if destination.exists() or destination.is_symlink():
        raise BackupSafetyError("Snapshot destination must not exist")
    if any(path.is_symlink() for path in (database, chroma, uploads)):
        raise BackupSafetyError("Snapshot sources must not be symlinks")
    if not database.is_file() or not chroma.is_dir() or not uploads.is_dir():
        raise BackupSafetyError(
            "Database, Chroma and upload source directories must exist"
        )
    database, chroma, uploads, destination = [
        path.resolve() for path in (database, chroma, uploads, destination)
    ]
    if destination.is_relative_to(chroma) or destination.is_relative_to(uploads):
        raise BackupSafetyError("Snapshot destination must be outside source trees")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".puchoo-backup-", dir=destination.parent))
    try:
        with database_lease(database):
            _sqlite_copy(database, stage / "auth.db")
            (stage / "datasets").mkdir(mode=0o700)
            mappings, copied = {}, {}
            with closing(_connection(stage / "auth.db")) as db:
                _authority(db)
                for workspace, kind, reference in db.execute(
                    "SELECT id, source_type, source_ref FROM workspace_records ORDER BY id"
                ):
                    if kind == "server":
                        continue  # Runtime-only credentials are never captured/reconnected.
                    if not reference:
                        raise BackupSafetyError(
                            "Local workspace has no dataset; resolve missing sources before backup"
                        )
                    source = Path(reference)
                    if not source.is_absolute() or source.is_symlink():
                        raise BackupSafetyError(
                            "Dataset source must be an absolute regular file"
                        )
                    source = source.resolve(strict=True)
                    if not source.is_relative_to(uploads) or not source.is_file():
                        raise BackupSafetyError(
                            "Dataset source lies outside the managed upload directory"
                        )
                    if source not in copied:
                        relative = f"datasets/{len(copied):06d}.db"
                        _sqlite_copy(source, stage / relative)
                        copied[source] = relative
                    mappings[workspace] = copied[source]
            before = _files(chroma)
            shutil.copytree(chroma, stage / "chroma", symlinks=True)
            if before != _files(chroma) or before != _files(stage / "chroma"):
                raise BackupSafetyError(
                    "Chroma changed during offline snapshot; stop all writers and retry"
                )
            for path in stage.rglob("*"):
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
            manifest = {
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "offline": True,
                "privacy_review_required": True,
                "datasets": mappings,
                "files": _files(stage),
            }
            (stage / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            os.chmod(stage / "manifest.json", 0o600)
            # A complete manifest is published only with the entire fresh tree.
            _publish(stage, destination)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _manifest(source):
    path = source / "manifest.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise BackupSafetyError(
            "Legacy/incomplete snapshot: versioned manifest required"
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or not isinstance(manifest.get("files"), dict)
            or not isinstance(manifest.get("datasets"), dict)
        ):
            raise ValueError
        if (
            type(manifest["version"]) is not int
            or manifest["version"] != 1
            or manifest["offline"] is not True
            or manifest["privacy_review_required"] is not True
        ):
            raise ValueError
        for relative in manifest["files"]:
            item = PurePosixPath(relative)
            if item.is_absolute() or ".." in item.parts or "\\" in relative:
                raise ValueError
        actual = _files(source)
        actual.pop("manifest.json", None)
        if actual != manifest["files"]:
            raise ValueError
        if "auth.db" not in actual or not (source / "chroma").is_dir():
            raise ValueError
        with closing(_connection(source / "auth.db")) as db:
            _authority(db)
            expected = {
                row[0]
                for row in db.execute(
                    "SELECT id FROM workspace_records WHERE source_type != 'server'"
                )
            }
        if set(manifest["datasets"]) != expected:
            raise ValueError
        for relative in manifest["datasets"].values():
            if relative not in actual or not relative.startswith("datasets/"):
                raise ValueError
    except (ValueError, KeyError, TypeError, sqlite3.DatabaseError) as exc:
        raise BackupSafetyError(
            "Snapshot manifest, hashes or dataset mapping are invalid"
        ) from exc
    return manifest


def restore_snapshot(source, destination, *, acknowledge_privacy_review=False):
    """Publish one fresh tree atomically; NEVER replace existing data.

    A point-in-time backup cannot know later deletions. Operator review of the
    latest deletion ledger (or offline vector purge/rebuild) is a hard gate.
    """
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise BackupSafetyError("Restore destination must not exist")
    if source.is_symlink() or not source.is_dir():
        raise BackupSafetyError("Snapshot source must be a real directory")
    if not acknowledge_privacy_review:
        raise BackupSafetyError(
            "Review deletions since this snapshot before restoring; explicit privacy acknowledgement required"
        )
    manifest = _manifest(source)
    source, destination = source.resolve(), destination.resolve()
    if destination.is_relative_to(source):
        raise BackupSafetyError("Restore must be outside the snapshot tree")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".puchoo-restore-", dir=destination.parent))
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True, symlinks=True)
        # Revalidate the copied bytes; do not trust paths/bytes changing during copy.
        _manifest(stage)
        _integrity(stage / "auth.db")
        for relative in set(manifest["datasets"].values()):
            _integrity(stage / relative)
        with closing(sqlite3.connect(stage / "auth.db")) as db:
            for workspace, relative in manifest["datasets"].items():
                db.execute(
                    "UPDATE workspace_records SET source_ref=? WHERE id=? AND source_type != 'server'",
                    (str(destination / relative), workspace),
                )
            db.commit()
        # No stale JSON is restored. SQL marker/generations/tombstones stay intact.
        (stage / "manifest.json").unlink()
        _publish(stage, destination)
        return {
            "database": destination / "auth.db",
            "chroma": destination / "chroma",
            "uploads": destination / "datasets",
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage)
