"""Restore the newest complete local Puchoo backup into fresh development paths."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path


class RestoreSafetyError(RuntimeError):
    """Raised before any restore write when a target is unsafe."""


def latest_complete_backup(backup_dir: Path) -> Path:
    candidates = sorted(
        (
            item
            for item in backup_dir.iterdir()
            if item.is_dir() and (item / "auth.db").is_file() and (item / "chroma").is_dir()
        ),
        key=lambda item: item.name,
    ) if backup_dir.is_dir() else []
    if not candidates:
        raise RestoreSafetyError("No complete SQLite and Chroma backup was found.")
    return candidates[-1]


def _safe_target(path: Path, label: str) -> None:
    if path.name == "puchoo_auth.db" or "production" in path.as_posix().lower():
        raise RestoreSafetyError(f"Refusing production-like {label} destination.")
    if path.exists():
        raise RestoreSafetyError(f"Restore {label} destination must not exist.")
    path.parent.mkdir(parents=True, exist_ok=True)


def _verify_sqlite(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if result != ("ok",):
        raise RestoreSafetyError("Restored SQLite database did not pass integrity_check.")


def restore_latest_backup(backup_dir: Path, target_database: Path, target_chroma_dir: Path) -> dict[str, Path]:
    """Copy the newest complete local backup only into two fresh destinations."""

    source = latest_complete_backup(Path(backup_dir))
    target_database = Path(target_database)
    target_chroma_dir = Path(target_chroma_dir)
    _safe_target(target_database, "database")
    _safe_target(target_chroma_dir, "Chroma")
    shutil.copy2(source / "auth.db", target_database)
    shutil.copytree(source / "chroma", target_chroma_dir)
    _verify_sqlite(target_database)
    return {"backup": source, "database": target_database, "chroma": target_chroma_dir}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--target-database", type=Path, required=True)
    parser.add_argument("--target-chroma-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = restore_latest_backup(args.backup_dir, args.target_database, args.target_chroma_dir)
    except RestoreSafetyError as exc:
        parser.error(str(exc))
    print(f"Restored {result['backup'].name} into fresh development targets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
