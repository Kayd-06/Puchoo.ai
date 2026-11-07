"""Restore a versioned complete snapshot into ONE fresh directory only."""

import argparse
from pathlib import Path
from backend.backups import BackupSafetyError, restore_snapshot

RestoreSafetyError = BackupSafetyError


def latest_complete_backup(backup_dir):
    candidates = sorted(
        path
        for path in Path(backup_dir).iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and (path / "manifest.json").is_file()
    )
    if not candidates:
        raise RestoreSafetyError(
            "No versioned complete backup found; legacy backups need manual review"
        )
    return candidates[-1]


def restore_latest_backup(backup_dir, destination, *, acknowledge_privacy_review=False):
    source = latest_complete_backup(backup_dir)
    # Do not silently fall back to an older snapshot if the latest is corrupt.
    return restore_snapshot(
        source, destination, acknowledge_privacy_review=acknowledge_privacy_review
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--acknowledge-privacy-review", action="store_true")
    args = parser.parse_args()
    try:
        restore_latest_backup(
            args.backup_dir,
            args.destination,
            acknowledge_privacy_review=args.acknowledge_privacy_review,
        )
    except (RestoreSafetyError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
