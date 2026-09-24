"""Workspace-scoped configuration and schema inspection helpers."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from io import BytesIO, TextIOWrapper
from itertools import chain
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

        dataframes = None if suffix == ".csv" else pd.read_excel(_bytes_reader(contents), sheet_name=None)
    except (OSError, UnicodeDecodeError, ValueError, ImportError, BadZipFile, pd.errors.EmptyDataError) as exc:
        if sqlite_path:
            sqlite_path.unlink(missing_ok=True)
        raise ValueError("The spreadsheet could not be read. Check that it is a valid CSV or Excel file.") from exc

    if suffix != ".csv" and not dataframes:
        raise ValueError("The uploaded spreadsheet contains no sheets or rows to query.")

    try:
        connection = sqlite3.connect(sqlite_path)
        try:
            _configure_bulk_import(connection)
            written_tables: set[str] = set()
            if suffix == ".csv":
                table_name = _unique_table_name(Path(filename).stem, written_tables)
                _write_csv_to_sql(connection, table_name, contents)
                written_tables.add(table_name)
            else:
                assert dataframes is not None
                for sheet_name, frame in dataframes.items():
                    if frame.empty and len(frame.columns) == 0:
                        continue
                    table_name = _unique_table_name(sheet_name, written_tables)
                    normalized = frame.copy()
                    normalized.columns = _unique_column_names(list(normalized.columns))
                    normalized.to_sql(table_name, connection, if_exists="fail", index=False)
                    written_tables.add(table_name)
            _create_analytical_indexes(connection, written_tables)
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


def create_tabular_collection_workspace(
    name: str,
    files: list[tuple[str, bytes]],
    *,
    storage_dir: Path | None = None,
) -> Workspace:
    """Combine multiple CSV/Excel uploads into one queryable SQLite workspace."""

    if not name or not name.strip():
        raise ValueError("Workspace name is required.")
    if not files:
        raise ValueError("Choose at least one CSV or Excel file.")

    destination = storage_dir or LOCAL_WORKSPACE_DIRECTORY
    destination.mkdir(parents=True, exist_ok=True)
    sqlite_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="pucho_collection_", suffix=".db", dir=destination, delete=False) as temporary_file:
            sqlite_path = Path(temporary_file.name)
        connection = sqlite3.connect(sqlite_path)
        try:
            _configure_bulk_import(connection)
            written_tables: set[str] = set()
            for filename, contents in files:
                if not contents:
                    raise ValueError(f"{filename} is empty.")
                suffix = Path(filename).suffix.lower()
                file_stem = Path(filename).stem
                if suffix == ".csv":
                    table_name = _unique_table_name(file_stem, written_tables)
                    _write_csv_to_sql(connection, table_name, contents)
                    written_tables.add(table_name)
                    continue
                elif suffix in {".xlsx", ".xls"}:
                    sheets = pd.read_excel(_bytes_reader(contents), sheet_name=None)
                    frames = {
                        f"{file_stem}_{sheet_name}": frame
                        for sheet_name, frame in sheets.items()
                    }
                else:
                    raise ValueError(f"Unsupported file format: {filename}")

                for source_name, frame in frames.items():
                    if frame.empty and len(frame.columns) == 0:
                        continue
                    table_name = _unique_table_name(source_name, written_tables)
                    normalized = frame.copy()
                    normalized.columns = _unique_column_names(list(normalized.columns))
                    normalized.to_sql(table_name, connection, if_exists="fail", index=False)
                    written_tables.add(table_name)
            _create_analytical_indexes(connection, written_tables)
            connection.commit()
        finally:
            connection.close()
    except (OSError, UnicodeDecodeError, ValueError, sqlite3.Error, ImportError, BadZipFile, pd.errors.EmptyDataError) as exc:
        if sqlite_path:
            sqlite_path.unlink(missing_ok=True)
        if isinstance(exc, ValueError) and str(exc).startswith(("Unsupported file format:",)):
            raise
        raise ValueError("The selected files could not be combined into a query workspace.") from exc

    if not written_tables:
        sqlite_path.unlink(missing_ok=True)
        raise ValueError("The selected files have no queryable columns.")
    workspace = create_sqlite_workspace(name, str(sqlite_path))
    return Workspace(
        id=workspace.id,
        name=workspace.name,
        database_uri=workspace.database_uri,
        dialect="sqlite",
        source_type="spreadsheet_collection",
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


def _configure_bulk_import(connection: sqlite3.Connection) -> None:
    """Tune a new, disposable workspace database for fast bulk ingestion."""

    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute("PRAGMA cache_size=-65536")


def _sqlite_type(values: list[str]) -> str:
    populated = [value.strip() for value in values if value.strip()]
    if not populated:
        return "TEXT"
    try:
        for value in populated:
            int(value)
        return "INTEGER"
    except ValueError:
        try:
            for value in populated:
                float(value)
            return "REAL"
        except ValueError:
            return "TEXT"


def _write_csv_to_sql(connection: sqlite3.Connection, table_name: str, contents: bytes) -> None:
    """Stream a CSV into SQLite in batches instead of materialising it in pandas."""

    stream = TextIOWrapper(BytesIO(contents), encoding="utf-8-sig", newline="")
    reader = csv.reader(stream)
    try:
        raw_columns = next(reader)
    except StopIteration as exc:
        raise ValueError("The uploaded CSV has no header row.") from exc
    if not raw_columns or not any(str(column).strip() for column in raw_columns):
        raise ValueError("The uploaded CSV has no queryable columns.")

    columns = _unique_column_names(list(raw_columns))
    sample = list(row for _, row in zip(range(1000), reader))
    normalized_sample = [_normalize_csv_row(row, len(columns)) for row in sample]
    types = [_sqlite_type([row[index] for row in normalized_sample]) for index in range(len(columns))]
    quoted_table = _quote_sqlite_identifier(table_name)
    definitions = ", ".join(
        f"{_quote_sqlite_identifier(column)} {column_type}" for column, column_type in zip(columns, types)
    )
    connection.execute(f"CREATE TABLE {quoted_table} ({definitions})")
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f"INSERT INTO {quoted_table} VALUES ({placeholders})"
    batch: list[list[object]] = []
    for row in chain(normalized_sample, (_normalize_csv_row(row, len(columns)) for row in reader)):
        batch.append([None if value == "" else value for value in row])
        if len(batch) >= 10_000:
            connection.executemany(insert_sql, batch)
            batch.clear()
    if batch:
        connection.executemany(insert_sql, batch)


def _normalize_csv_row(row: list[str], width: int) -> list[str]:
    if len(row) < width:
        return row + [""] * (width - len(row))
    return row[:width]


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _create_analytical_indexes(connection: sqlite3.Connection, tables: set[str]) -> None:
    """Index common join/filter columns without guessing business-specific fields."""

    for table in tables:
        quoted_table = _quote_sqlite_identifier(table)
        columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted_table})")]
        for column in columns:
            lowered = column.lower()
            if not lowered.endswith(("_id", "_date", "_status")):
                continue
            index_name = _safe_identifier(f"idx_{table}_{column}", "idx_column")
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS {_quote_sqlite_identifier(index_name)} "
                f"ON {quoted_table} ({_quote_sqlite_identifier(column)})"
            )
    connection.execute("PRAGMA optimize")


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
    engine = None
    try:
        engine = create_engine(database_uri)
        inspector = inspect(engine)
        lines: list[str] = []
        column_tables: dict[str, list[str]] = {}
        categorical_suffixes = ("status", "type", "category", "method")
        connection = engine.connect() if database_uri.startswith("sqlite") else None
        preparer = engine.dialect.identifier_preparer
        for table in inspector.get_table_names():
            columns = inspector.get_columns(table)
            fields = ", ".join(f"{column['name']} ({column['type']})" for column in columns)
            table_lines = [f"Table: {table}", f"Columns: {fields}"]
            for column in columns:
                column_name = str(column["name"])
                column_tables.setdefault(column_name, []).append(table)
                if connection is not None and column_name.lower().endswith(categorical_suffixes):
                    quoted_table = preparer.quote(table)
                    quoted_column = preparer.quote(column_name)
                    values = connection.execute(text(
                        f"SELECT DISTINCT {quoted_column} FROM {quoted_table} "
                        f"WHERE {quoted_column} IS NOT NULL LIMIT 13"
                    )).scalars().all()
                    if 0 < len(values) <= 12:
                        table_lines.append(
                            f"Values for {column_name}: " + ", ".join(repr(str(value)) for value in values)
                        )
            lines.append("\n".join(table_lines))
        if connection is not None:
            connection.close()
        join_hints = [
            f"{column}: " + ", ".join(f"{table}.{column}" for table in tables)
            for column, tables in column_tables.items()
            if column.endswith("_id") and len(tables) > 1
        ]
        if join_hints:
            lines.append("Join candidates (same key name; use only when relevant):\n" + "\n".join(join_hints))
    except (SQLAlchemyError, ModuleNotFoundError, ImportError) as exc:
        raise ValueError("Could not read the workspace database schema.") from exc
    finally:
        if engine is not None:
            engine.dispose()
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
