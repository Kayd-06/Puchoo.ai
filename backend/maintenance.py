"""Offline SQLite maintenance gate, shared by API lifespans and backup jobs."""

from contextlib import contextmanager, nullcontext
from pathlib import Path
import os


@contextmanager
def database_lease(database: Path, *, shared=False):
    path = Path(str(Path(database).resolve()) + ".maintenance.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("Maintenance lock must not be a symlink")
    descriptor = os.open(
        path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    stream = os.fdopen(descriptor, "r+b")
    try:
        try:
            if os.name == "posix":
                import fcntl

                fcntl.flock(
                    stream, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB
                )
            elif os.name == "nt":
                import msvcrt

                if path.stat().st_size == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(
                    stream.fileno(), msvcrt.LK_NBRLCK if shared else msvcrt.LK_NBLCK, 1
                )
            else:
                raise RuntimeError(
                    "Offline maintenance locking is unsupported on this platform"
                )
        except OSError:
            raise RuntimeError(
                "Database is in use. Stop all API/writer processes before maintenance."
            ) from None
        yield
    finally:
        stream.close()


def api_database_lease():
    from backend import database

    url = database.engine.url
    if url.get_backend_name() == "sqlite" and url.database not in {None, ":memory:"}:
        return database_lease(Path(url.database), shared=True)
    return nullcontext()
