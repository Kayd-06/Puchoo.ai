"""Workspace-scoped configuration and schema inspection helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import sqlite3
import tempfile
from zipfile import BadZipFile
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus
from uuid import uuid4

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_WORKSPACE_DIRECTORY = PROJECT_ROOT / ".pucho" / "workspaces"


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    database_uri: str
    dialect: str = "sqlite"
    source_type: str = "file"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def sqlite_uri(database_path: str) -> str:
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError("Choose an existing SQLite database file.")
    return f"sqlite:///{path}"


def create_sqlite_workspace(name: str, database_path: str) -> Workspace:
    if not name or not name.strip():
        raise ValueError("Workspace name is required.")
    uri = sqlite_uri(database_path)
    # Prove that the workspace can inspect the selected file before saving it.
    get_schema_snapshot(uri)
    return Workspace(id=f"ws_{uuid4().hex[:12]}", name=name.strip(), database_uri=uri)


def create_uploaded_sqlite_workspace(name: str, filename: str, contents: bytes) -> Workspace:
    """Persist a user-uploaded SQLite file in Pucho's local workspace store."""

    if not name or not name.strip():
        raise ValueError("Workspace name is required.")
    if not contents:
        raise ValueError("The uploaded database file is empty.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Upload a SQLite .db, .sqlite, or .sqlite3 file.")
    LOCAL_WORKSPACE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="pucho_source_", suffix=suffix, dir=LOCAL_WORKSPACE_DIRECTORY, delete=False) as temporary_file:
        temporary_file.write(contents)
        uploaded_path = temporary_file.name
    try:
        return create_sqlite_workspace(name, uploaded_path)
    except ValueError:
        Path(uploaded_path).unlink(missing_ok=True)
        raise


def create_tabular_workspace(
    name: str, filename: str, contents: bytes, *, storage_dir: Path | None = None
) -> Workspace:
    """Create a session-local SQLite workspace from an uploaded CSV/XLSX file.

    The original upload is never sent to a remote service.  Only the derived
    local SQLite file is used by the read-only query executor.
    """

    if not name or not name.strip():
        raise ValueError("Workspace name is required.")
    if not contents:
        raise ValueError("The uploaded file is empty.")

    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise ValueError("Upload a CSV, XLSX, or XLS file.")

    sqlite_path: Path | None = None
    try:
        destination = storage_dir or LOCAL_WORKSPACE_DIRECTORY
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="pucho_import_", suffix=".db", dir=destination, delete=False) as temporary_file:
            sqlite_path = Path(temporary_file.name)

        if suffix == ".csv":
            frame = pd.read_csv(_bytes_reader(contents))
            dataframes = {Path(filename).stem: frame}
        else:
            dataframes = pd.read_excel(_bytes_reader(contents), sheet_name=None)
    except (OSError, UnicodeDecodeError, ValueError, ImportError, BadZipFile, pd.errors.EmptyDataError) as exc:
        if sqlite_path:
            sqlite_path.unlink(missing_ok=True)
        raise ValueError("The spreadsheet could not be read. Check that it is a valid CSV or Excel file.") from exc

    if not dataframes:
        raise ValueError("The uploaded spreadsheet contains no sheets or rows to query.")

    try:
        connection = sqlite3.connect(sqlite_path)
        try:
            written_tables: set[str] = set()
            for sheet_name, frame in dataframes.items():
                if frame.empty and len(frame.columns) == 0:
                    continue
                table_name = _unique_table_name(sheet_name, written_tables)
                normalized = frame.copy()
                normalized.columns = _unique_column_names(list(normalized.columns))
                normalized.to_sql(table_name, connection, if_exists="fail", index=False)
                written_tables.add(table_name)
            connection.commit()
        finally:
            connection.close()
    except (sqlite3.Error, ValueError) as exc:
        sqlite_path.unlink(missing_ok=True)
        raise ValueError("The spreadsheet could not be converted into a query workspace.") from exc

    if not written_tables:
        sqlite_path.unlink(missing_ok=True)
        raise ValueError("The uploaded spreadsheet has no queryable columns.")
    workspace = create_sqlite_workspace(name, str(sqlite_path))
    return Workspace(
        id=workspace.id,
        name=workspace.name,
        database_uri=workspace.database_uri,
        dialect="sqlite",
        source_type="spreadsheet",
    )


def create_server_workspace(
    name: str,
    *,
    engine: Literal["postgresql", "mysql"],
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    ssl_required: bool,
) -> Workspace:
    """Validate and connect a server workspace using discrete connection fields.

    Passwords are kept only in the current Streamlit server session. A database
    role with read-only permissions is still required; app-side guardrails are
    an additional protection, not a substitute for database permissions.
    """

    if not name or not name.strip():
        raise ValueError("Workspace name is required.")
    if engine not in {"postgresql", "mysql"}:
        raise ValueError("Choose PostgreSQL or MySQL.")
    if not host.strip() or not database.strip() or not username.strip():
        raise ValueError("Host, database name, and username are required.")
    if not password:
        raise ValueError("Password is required for a database-server connection.")
    if not 1 <= int(port) <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", host.strip()):
        raise ValueError("Host may contain only a hostname, IPv4 address, or IPv6 address.")

    driver = "postgresql+psycopg" if engine == "postgresql" else "mysql+pymysql"
    encoded_user = quote_plus(username.strip())
    encoded_password = quote_plus(password)
    uri = f"{driver}://{encoded_user}:{encoded_password}@{host.strip()}:{int(port)}/{database.strip()}"
    if ssl_required:
        uri += "?sslmode=require" if engine == "postgresql" else "?ssl=true"

    # Test schema access before this workspace becomes selectable.
    get_schema_snapshot(uri)
    return Workspace(
        id=f"ws_{uuid4().hex[:12]}",
        name=name.strip(),
        database_uri=uri,
        dialect=engine,
        source_type="server",
    )


def _bytes_reader(contents: bytes):
    """Avoid persisting raw user uploads while pandas parses them."""

    from io import BytesIO

    return BytesIO(contents)


def _safe_identifier(value: object, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", str(value).strip()).strip("_").lower()
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized[:63]


def _unique_table_name(value: object, existing: set[str]) -> str:
    base = _safe_identifier(value, "sheet")
    candidate, index = base, 2
    while candidate in existing:
        candidate = f"{base[:56]}_{index}"
        index += 1
    return candidate


def _unique_column_names(columns: list[object]) -> list[str]:
    used: set[str] = set()
    result: list[str] = []
    for index, column in enumerate(columns, start=1):
        base = _safe_identifier(column, f"column_{index}")
        candidate, suffix = base, 2
        while candidate in used:
            candidate = f"{base[:56]}_{suffix}"
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result


def get_schema_snapshot(database_uri: str) -> str:
    try:
        engine = create_engine(database_uri)
        inspector = inspect(engine)
        lines: list[str] = []
        for table in inspector.get_table_names():
            fields = ", ".join(f"{column['name']} ({column['type']})" for column in inspector.get_columns(table))
            lines.append(f"Table: {table}\nColumns: {fields}")
        engine.dispose()
    except (SQLAlchemyError, ModuleNotFoundError, ImportError) as exc:
        raise ValueError("Could not read the workspace database schema.") from exc
    if not lines:
        raise ValueError("The selected database has no tables to query.")
    return "\n\n".join(lines)


def get_schema_metrics(database_uri: str) -> dict[str, int]:
    """Return live table/column counts without reading source-table rows."""

    try:
        engine = create_engine(database_uri)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        columns = sum(len(inspector.get_columns(table)) for table in tables)
        engine.dispose()
        return {"tables": len(tables), "columns": columns}
    except (SQLAlchemyError, ModuleNotFoundError, ImportError) as exc:
        raise ValueError("Could not inspect the workspace database.") from exc


def get_schema_table_stats(database_uri: str, *, include_row_counts: bool = False) -> list[dict[str, int | str | None]]:
    """Return live schema statistics for the connected source.

    Counting every row can be costly on a remote analytical server, so callers
    opt in only for local uploaded sources. Table and column values always come
    from the current database metadata; no display data is synthesized.
    """

    engine = None
    try:
        engine = create_engine(database_uri)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        stats: list[dict[str, int | str | None]] = []
        with engine.connect() as connection:
            preparer = engine.dialect.identifier_preparer
            for table in tables:
                row_count: int | None = None
                if include_row_counts:
                    quoted_table = preparer.quote(table)
                    row_count = int(connection.execute(text(f"SELECT COUNT(*) FROM {quoted_table}")).scalar_one())
                stats.append({"name": table, "columns": len(inspector.get_columns(table)), "rows": row_count})
        return stats
    except (SQLAlchemyError, ModuleNotFoundError, ImportError) as exc:
        raise ValueError("Could not inspect the workspace tables.") from exc
    finally:
        if engine is not None:
            engine.dispose()
