"""Create one versioned offline SQLite/datasets/Chroma snapshot."""

import argparse
from pathlib import Path
from backend.backups import create_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "chroma", "uploads", "destination"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--writers-stopped",
        action="store_true",
        help="Confirm all API, indexing and maintenance writer processes have exited",
    )
    args = parser.parse_args()
    create_snapshot(
        args.database,
        args.chroma,
        args.uploads,
        args.destination,
        writers_stopped=args.writers_stopped,
    )


if __name__ == "__main__":
    main()
