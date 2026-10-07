"""SQLAlchemy engine and session factory. SQLite for development, Postgres via DATABASE_URL."""

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None


def make_engine(url: str):
    connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    created = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.startswith("sqlite"):

        @event.listens_for(created, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return created


def configure_database(url: str | None = None) -> None:
    """Point the process at a database URL. Tests call this with a temporary SQLite file."""

    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
    engine = make_engine(url or settings.database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend import models  # noqa: F401

    # Existing databases must run migrations: create_all() never adds a new
    # column to an existing table, which previously broke invite creation.
    if inspect(engine).has_table("alembic_version"):
        command.upgrade(_alembic_config(), "head")
        return

    # A fresh database can be created directly from current metadata, then
    # stamped so every later startup follows the migration path.
    Base.metadata.create_all(bind=engine)
    command.stamp(_alembic_config(), "head")


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parent
    config = Config(str(backend_dir / "alembic.ini"))
    # Alembic's CLI logging config must not replace the application's logging
    # handlers when migrations run inside API startup.
    config.config_file_name = None
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    database_url = engine.url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


configure_database()
