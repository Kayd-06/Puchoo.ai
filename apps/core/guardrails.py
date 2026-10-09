"""AST-based read-only SQL guardrails for untrusted SQL proposals.

Model output is never trusted. Every proposal is parsed with sqlglot and must be
one SELECT (CTEs and UNION/INTERSECT/EXCEPT of SELECTs are fine). The checks are
allowlists, not blocklists:

* only known-safe functions (aggregates, math, string, date/time, conditional,
  CAST and window functions) may be called; everything else is rejected,
* only tables from the active data source (or CTEs) may be read; system
  schemas and catalog tables are always rejected,
* SELECT INTO / INTO OUTFILE, row locks, session variables, bind parameters,
  qualified function calls and executable comments are rejected.

The SQL that is approved and executed is always sqlglot's re-rendering of the
validated AST with comments removed, so nothing the parser skipped (for example
a MySQL ``/*! ... */`` comment) can reach the database.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

try:
    from sqlglot import exp, parse
    from sqlglot.errors import ErrorLevel, ParseError, TokenError, UnsupportedError
    from sqlglot.tokens import Tokenizer
    from sqlglot.dialects.dialect import Dialect
except ImportError:  # pragma: no cover - only reached without installed dependencies
    exp = None  # type: ignore[assignment]
    parse = None  # type: ignore[assignment]
    Dialect = None  # type: ignore[assignment]
    Tokenizer = None  # type: ignore[assignment]
    ErrorLevel = None  # type: ignore[assignment]
    ParseError = Exception
    TokenError = Exception
    UnsupportedError = Exception


class SQLGuardrailError(ValueError):
    """Raised when untrusted SQL fails a server-side safety policy.

    Messages are written for end users and never include database errors.
    """


class SQLParseError(SQLGuardrailError):
    """Raised when model output is incomplete or malformed, but not executable."""


# Workspace records say "postgresql". sqlglot's dialect name is "postgres".
_SQLGLOT_DIALECTS = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
}

MAX_SQL_LENGTH = 20_000


def sqlglot_dialect(dialect: str | None) -> str | None:
    """Return the sqlglot name for a workspace dialect."""

    if dialect is None:
        return None
    normalized = dialect.strip().lower()
    if not normalized:
        return None
    return _SQLGLOT_DIALECTS.get(normalized, normalized)


@dataclass(frozen=True)
class GuardedSQL:
    sql: str
    limit: int
    # True when the guardrail added or lowered the outer LIMIT. A result with
    # exactly ``limit`` rows may then be truncated.
    limit_clamped: bool = False


@dataclass(frozen=True)
class SchemaCatalog:
    """Tables and columns discovered from the active data source.

    Table and column names are compared case-insensitively. ``qualifiers``
    lists the schema or database names a table may be prefixed with (for
    example ``public``), exactly as the database reports them; they are
    compared with each dialect's identifier rules (see ``_qualifier_name``).
    """

    tables: Mapping[str, frozenset[str]]
    qualifiers: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_mapping(
        cls, tables: Mapping[str, Iterable[str]], *, qualifiers: Iterable[str | None] = ()
    ) -> "SchemaCatalog":
        return cls(
            tables={str(name).lower(): frozenset(str(column).lower() for column in columns) for name, columns in tables.items()},
            qualifiers=frozenset(str(item) for item in qualifiers if item),
        )

    @property
    def columns(self) -> frozenset[str]:
        return frozenset(column for columns in self.tables.values() for column in columns)


# --- Policy -----------------------------------------------------------------

# A SELECT root is necessary but insufficient: PostgreSQL has data-changing CTEs
# and SELECT INTO writes a table. Reject these nodes anywhere in the AST.
_DISALLOWED_AST_NODES = (
    "Alter", "Analyze", "Attach", "Cache", "Command", "Commit", "Copy", "Create",
    "Delete", "Detach", "Drop", "Execute", "Grant", "Insert", "LoadData",
    "Merge", "Pragma", "Rename", "Revoke", "Rollback", "Set", "Transaction",
    "TruncateTable", "Uncache", "Update", "Use", "Vacuum", "Summarize", "Describe",
    "Show", "Kill", "Refresh", "Comment",
)

# sqlglot parses many functions into typed nodes. These are safe in every
# supported dialect: they read the row values they are given and nothing else.
_ALLOWED_FUNCTION_NODES = frozenset({
    # Aggregates
    "Count", "CountIf", "Sum", "Avg", "Min", "Max", "GroupConcat", "Stddev", "StddevPop",
    "StddevSamp", "Variance", "VariancePop", "Median", "PercentileCont", "PercentileDisc",
    "ApproxDistinct", "Corr", "CovarPop", "CovarSamp", "LogicalAnd", "LogicalOr", "AnyValue",
    # Math
    "Abs", "Ceil", "Floor", "Round", "Pow", "Sqrt", "Cbrt", "Exp", "Ln", "Log", "Sign",
    "Greatest", "Least", "SafeDivide", "ToNumber", "ToDouble",
    # Strings
    "Lower", "Upper", "Length", "Substring", "Trim", "Concat", "ConcatWs", "SplitPart",
    "Left", "Right", "StrPosition", "Initcap", "StartsWith",
    # Date and time
    "CurrentDate", "CurrentTime", "CurrentTimestamp", "CurrentDatetime", "Date", "Datetime",
    "Time", "Timestamp", "DateAdd", "DateSub", "DateDiff", "DateTrunc", "DatetimeAdd",
    "DatetimeSub", "DatetimeDiff", "DatetimeTrunc", "TimestampAdd", "TimestampSub",
    "TimestampDiff", "TimestampTrunc", "TimeAdd", "TimeSub", "TimeDiff", "TimeTrunc",
    "Extract", "Year", "Quarter", "Month", "Week", "WeekOfYear", "Day", "DayOfMonth",
    "DayOfWeek", "DayOfWeekIso", "DayOfYear", "LastDay", "AddMonths", "MonthsBetween",
    "StrToDate", "StrToTime", "StrToUnix", "TimeToStr", "TimeToUnix", "TimeStrToTime",
    "TimeStrToDate", "TimeStrToUnix", "TimeToTimeStr", "UnixToTime", "UnixToStr",
    "UnixToTimeStr", "DateStrToDate", "DateToDateStr", "DateFromParts", "TsOrDsAdd",
    "TsOrDsDiff", "TsOrDsToDate", "TsOrDsToDateStr", "TsOrDsToDatetime", "TsOrDsToTime",
    "TsOrDsToTimestamp", "ToChar", "MakeInterval",
    # Conditional and casts
    "Case", "If", "Coalesce", "Nullif", "Nvl2", "Cast", "TryCast", "Exists", "Collate",
    # Window functions
    "RowNumber", "Lag", "Lead", "FirstValue", "LastValue", "NthValue",
})

# Padding/formatting functions that can allocate huge strings in one call
# (lpad, rpad, printf, format, repeat) are deliberately absent.
#
# Functions sqlglot does not model leave an ``Anonymous`` node. Only these
# names, per dialect, may be called. Compared case-insensitively.
_COMMON_ANONYMOUS = frozenset({
    "rank", "dense_rank", "ntile", "percent_rank", "cume_dist",
    "replace", "ltrim", "rtrim", "char_length", "character_length",
    "ifnull", "nullif", "mod", "power", "ceiling", "trunc", "truncate",
    "hour", "minute", "second", "now",
})
_DIALECT_ANONYMOUS: dict[str | None, frozenset[str]] = {
    "sqlite": frozenset({
        "julianday", "strftime", "date", "time", "datetime", "unixepoch",
        "instr", "total", "typeof", "iif", "substr",
    }),
    "postgres": frozenset({
        "age", "date_part", "to_char", "to_date", "to_timestamp", "to_number", "make_date",
        "btrim", "strpos", "position", "width_bucket", "div", "mode", "string_agg",
        "justify_days", "justify_hours", "justify_interval", "date_bin",
    }),
    "mysql": frozenset({
        "curdate", "curtime", "dayname", "monthname", "yearweek", "weekday", "date_format",
        "str_to_date", "from_unixtime", "unix_timestamp", "substring_index", "instr", "locate",
        "makedate", "period_diff", "timestampdiff", "datediff",
    }),
}

# Never allowed, whatever an allowlist says. Kept explicit for clearer errors
# and as a regression list for tests. Compared case-insensitively.
DANGEROUS_FUNCTIONS: dict[str, frozenset[str]] = {
    "postgres": frozenset({
        "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_read_file", "pg_read_binary_file",
        "pg_ls_dir", "pg_stat_file", "lo_import", "lo_export", "lo_get", "lo_from_bytea",
        "dblink", "dblink_exec", "dblink_connect", "dblink_send_query", "set_config",
        "current_setting", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
        "pg_advisory_lock", "query_to_xml", "query_to_xml_and_xmlschema", "table_to_xml",
        "copy", "nextval", "setval", "txid_current", "version", "inet_server_addr",
        "pg_logical_emit_message", "pg_switch_wal", "pg_create_restore_point",
    }),
    "mysql": frozenset({
        "sleep", "benchmark", "load_file", "get_lock", "release_lock", "sys_exec", "sys_eval",
        "master_pos_wait", "source_pos_wait", "version", "database", "user", "current_user",
        "system_user", "session_user", "connection_id", "uuid_short", "extractvalue", "updatexml",
    }),
    "sqlite": frozenset({
        "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer", "randomblob",
        "zeroblob", "sqlite_version", "sqlite_source_id", "sqlite_compileoption_used",
        "sqlite_compileoption_get", "sqlite_offset",
    }),
    "*": frozenset({"xp_cmdshell", "xp_regread", "xp_dirtree", "sp_executesql", "openrowset", "opendatasource"}),
}

_SYSTEM_SCHEMAS = frozenset({
    "pg_catalog", "information_schema", "pg_toast", "mysql", "performance_schema", "sys",
    "temp", "sqlite_temp", "pg_temp",
})
_SYSTEM_TABLE_PREFIXES = ("pg_", "sqlite_", "pragma_", "information_schema")
_SYSTEM_TABLES = frozenset({"dual", "dbstat"})
# Unquoted, unqualified "columns" that the database evaluates as session
# functions (PostgreSQL ``SELECT session_user``, MySQL ``SELECT current_user``).
_SESSION_KEYWORDS = frozenset({
    "user", "current_user", "session_user", "system_user", "current_role",
    "current_catalog", "current_schema",
})
# Qualifiers that always mean "the connected database" for that dialect.
_DEFAULT_QUALIFIERS: dict[str | None, frozenset[str]] = {
    "sqlite": frozenset({"main"}),
    "postgres": frozenset({"public"}),
    "mysql": frozenset(),
}


def _require_sqlglot() -> None:
    if parse is None or exp is None:
        raise RuntimeError(
            "sqlglot is required for SQL guardrails. Install dependencies with `pip install -r requirements.txt`."
        )


def _short(name: str) -> str:
    cleaned = "".join(character for character in str(name) if character.isprintable())
    return cleaned if len(cleaned) <= 64 else cleaned[:61] + "..."


def _reject_unsafe_characters(sql: str) -> None:
    """Reject invisible and control characters.

    Bidi overrides and zero-width characters can make the SQL a user approves
    look different from the SQL that runs ("Trojan Source").
    """

    for character in sql:
        if character in "\t\n\r":
            continue
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Co", "Cs", "Zl", "Zp"} or (category == "Zs" and character != " "):
            raise SQLGuardrailError(
                "The SQL contains invisible or control characters. Please rephrase the question."
            )


def _reject_executable_comments(sql: str, dialect: str | None) -> None:
    """Reject comments a database may execute (MySQL ``/*! */``, optimizer hints)."""

    try:
        tokens = Dialect.get_or_raise(dialect).tokenize(sql) if dialect else Tokenizer().tokenize(sql)
    except (TokenError, ParseError, ValueError) as exc:
        raise SQLParseError("The SQL could not be parsed.") from exc
    for token in tokens:
        for comment in token.comments or ():
            stripped = comment.lstrip()
            if stripped.startswith(("!", "+", "M!")):
                raise SQLGuardrailError("Executable comments and optimizer hints are not allowed.")
    # A ``/*!`` comment that the tokenizer folded into something else is still refused.
    lowered = sql.lower()
    if "/*!" in lowered or "/*+" in lowered or "/*m!" in lowered:
        raise SQLGuardrailError("Executable comments and optimizer hints are not allowed.")


def _parse_single_query(sql: str, dialect: str | None) -> Any:
    if not isinstance(sql, str) or not sql.strip():
        raise SQLParseError("SQL must be a non-empty string.")
    if len(sql) > MAX_SQL_LENGTH:
        raise SQLGuardrailError("The SQL is too long to run safely.")
    _require_sqlglot()
    _reject_unsafe_characters(sql)
    _reject_executable_comments(sql, dialect)
    try:
        statements = [statement for statement in parse(sql, read=dialect) if statement is not None]
    except (ParseError, TokenError) as exc:
        raise SQLParseError("The SQL could not be parsed.") from exc
    except RecursionError as exc:
        raise SQLGuardrailError("The SQL is nested too deeply to run safely.") from exc
    if len(statements) != 1:
        raise SQLGuardrailError("Only one SQL statement can run at a time.")
    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.SetOperation)):
        raise SQLGuardrailError("Only a single read-only SELECT query can run.")
    return statement


def _cte_names(node: Any) -> set[str]:
    """CTE names visible to ``node``: those defined by any enclosing WITH."""

    names: set[str] = set()
    current = node
    while current is not None:
        with_clause = current.args.get("with") if isinstance(current, exp.Expression) else None
        if isinstance(with_clause, exp.With):
            names.update(cte.alias.lower() for cte in with_clause.expressions if cte.alias)
        current = current.parent
    return names


def _is_system_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in _SYSTEM_SCHEMAS or lowered in _SYSTEM_TABLES or lowered.startswith(_SYSTEM_TABLE_PREFIXES)


def _qualifier_name(identifier: Any, dialect: str | None) -> str:
    """The name a database resolves a schema qualifier to.

    PostgreSQL folds unquoted names to lower case but keeps quoted names
    exactly, so ``"Public"`` is a different schema from ``public``. MySQL
    database names can be case-sensitive, so they must match exactly. SQLite
    schema names are case-insensitive.
    """

    name = str(identifier.this if isinstance(identifier, exp.Identifier) else identifier or "")
    quoted = bool(isinstance(identifier, exp.Identifier) and identifier.args.get("quoted"))
    if dialect == "postgres":
        return name if quoted else name.lower()
    if dialect == "mysql":
        return name
    return name.lower()


def _allowed_qualifiers(dialect: str | None, catalog: SchemaCatalog | None) -> frozenset[str]:
    if catalog is not None and catalog.qualifiers:
        reported = catalog.qualifiers if dialect in {"postgres", "mysql"} else frozenset(
            item.lower() for item in catalog.qualifiers
        )
        # SQLite's main database is always reachable as ``main``.
        return reported | (_DEFAULT_QUALIFIERS["sqlite"] if dialect == "sqlite" else frozenset())
    return _DEFAULT_QUALIFIERS.get(dialect, frozenset())


def _function_name(node: Any) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name)
    return node.sql_name() if hasattr(node, "sql_name") else type(node).__name__


def _check_function(node: Any, dialect: str | None) -> None:
    dangerous = DANGEROUS_FUNCTIONS.get(dialect or "", frozenset()) | DANGEROUS_FUNCTIONS["*"]
    if isinstance(node, exp.Anonymous):
        name = str(node.name or "")
        lowered = name.lower()
        if lowered in dangerous or lowered.startswith(("xp_", "sp_", "pg_", "lo_", "dblink", "sqlite_")):
            raise SQLGuardrailError(
                f"The function {_short(name)}() is blocked because it can reach the server, files, or session state."
            )
        if lowered in _COMMON_ANONYMOUS or lowered in _DIALECT_ANONYMOUS.get(dialect, frozenset()):
            return
        raise SQLGuardrailError(f"The function {_short(name)}() is not on Puchoo.si's list of allowed functions.")
    if type(node).__name__ in _ALLOWED_FUNCTION_NODES:
        return
    raise SQLGuardrailError(
        f"The function {_short(_function_name(node))}() is not on Puchoo.si's list of allowed functions."
    )


def _alias_names(statement: Any) -> set[str]:
    names: set[str] = set()
    for node in statement.walk():
        if isinstance(node, exp.Alias) and node.alias:
            names.add(node.alias.lower())
        elif isinstance(node, exp.TableAlias):
            if node.name:
                names.add(node.name.lower())
            names.update(column.name.lower() for column in node.columns if getattr(column, "name", None))
        elif isinstance(node, exp.CTE) and node.alias:
            names.add(node.alias.lower())
    return names


def _check_table(node: Any, dialect: str | None, catalog: SchemaCatalog | None) -> None:
    if not isinstance(node.this, exp.Identifier):
        raise SQLGuardrailError("Table functions are not allowed. Query the data source's tables directly.")
    name = str(node.name or "")
    if node.args.get("catalog") is not None and node.catalog:
        raise SQLGuardrailError(f"Cross-database references such as {_short(node.catalog)}.{_short(node.db)} are not allowed.")
    qualifier = str(node.db or "")
    if qualifier:
        if _is_system_name(qualifier):
            raise SQLGuardrailError(f"System schemas such as {_short(qualifier)} cannot be queried.")
        if _qualifier_name(node.args.get("db"), dialect) not in _allowed_qualifiers(dialect, catalog):
            raise SQLGuardrailError(f"The schema {_short(qualifier)} is not part of this data source.")
    if _is_system_name(name):
        raise SQLGuardrailError(f"System tables such as {_short(name)} cannot be queried.")
    if catalog is None:
        return
    if not qualifier and name.lower() in _cte_names(node):
        return
    if name.lower() not in catalog.tables:
        raise SQLGuardrailError(f"The table {_short(name)} is not part of this data source.")


def _check_tree(statement: Any, dialect: str | None, catalog: SchemaCatalog | None) -> None:
    blocked_types = tuple(
        node_type for name in _DISALLOWED_AST_NODES if (node_type := getattr(exp, name, None)) is not None
    )
    aliases = _alias_names(statement) if catalog is not None else set()
    known_columns = catalog.columns if catalog is not None else frozenset()
    for node in statement.walk():
        if isinstance(node, exp.Into):
            raise SQLGuardrailError("SELECT INTO, INTO OUTFILE and INTO DUMPFILE are not allowed.")
        if isinstance(node, exp.Lock):
            raise SQLGuardrailError("Row locks such as FOR UPDATE or FOR SHARE are not allowed.")
        if blocked_types and isinstance(node, blocked_types):
            raise SQLGuardrailError("Only read-only SELECT SQL is allowed.")
        if isinstance(node, (exp.Parameter, exp.SessionParameter, exp.Placeholder)):
            raise SQLGuardrailError("Variables, session settings and bind parameters are not allowed.")
        if getattr(exp, "Operator", None) is not None and isinstance(node, exp.Operator):
            raise SQLGuardrailError("Explicit OPERATOR(...) calls are not allowed.")
        if isinstance(node, exp.In) and node.args.get("field") is not None:
            # SQLite's ``x IN table_name`` reads a table that looks like a column.
            raise SQLGuardrailError("Use IN (SELECT ...) instead of IN table_name.")
        if isinstance(node, exp.Dot):
            raise SQLGuardrailError("Schema-qualified function calls and nested field access are not allowed.")
        if isinstance(node, exp.ObjectIdentifier) or (
            isinstance(node, exp.DataType) and node.this == exp.DataType.Type.USERDEFINED
        ):
            raise SQLGuardrailError("Casting to system or user-defined types is not allowed.")
        if isinstance(node, exp.Func):
            _check_function(node, dialect)
        elif isinstance(node, exp.Table):
            _check_table(node, dialect, catalog)
        elif isinstance(node, exp.CTE) and node.alias and _is_system_name(node.alias):
            raise SQLGuardrailError(f"A CTE cannot reuse a system table name such as {_short(node.alias)}.")
        elif isinstance(node, exp.Column):
            if node.args.get("db") is not None or node.args.get("catalog") is not None:
                raise SQLGuardrailError("Columns may only be qualified by a table name or alias.")
            if node.table and _is_system_name(node.table):
                raise SQLGuardrailError(f"System tables such as {_short(node.table)} cannot be queried.")
            identifier = node.this
            if isinstance(identifier, exp.Identifier) and not identifier.args.get("quoted"):
                bare = str(identifier.this or "")
                if not node.table and bare.lower() in _SESSION_KEYWORDS:
                    raise SQLGuardrailError(f"Session details such as {_short(bare)} cannot be queried.")
                if bare[:1] in {"$", "@", ":", "?"}:
                    raise SQLGuardrailError("Variables, session settings and bind parameters are not allowed.")
            if catalog is not None and not isinstance(node.this, exp.Star):
                column = str(node.name or "").lower()
                if column and column not in known_columns and column not in aliases:
                    raise SQLGuardrailError(f"The column {_short(node.name)} is not part of this data source.")


def _limit_value(limit_expression: Any) -> int | None:
    """Return a non-negative literal LIMIT, or ``None`` for non-literals."""

    if not isinstance(limit_expression, exp.Limit):
        return None
    expression = limit_expression.args.get("expression")
    if not isinstance(expression, exp.Literal) or expression.is_string:
        return None
    try:
        value = int(expression.this)
    except (AttributeError, TypeError, ValueError):
        return None
    return value if value >= 0 else None


@dataclass(frozen=True)
class SQLGuardrails:
    """Validate a single SELECT and cap only its outermost result limit."""

    max_limit: int = 500
    dialect: str | None = "sqlite"
    catalog: SchemaCatalog | None = None

    def __post_init__(self) -> None:
        if isinstance(self.max_limit, bool) or not isinstance(self.max_limit, int) or self.max_limit <= 0:
            raise ValueError("max_limit must be a positive integer")
        object.__setattr__(self, "dialect", sqlglot_dialect(self.dialect))

    def _validated(self, sql: str) -> Any:
        statement = _parse_single_query(sql, self.dialect)
        _check_tree(statement, self.dialect, self.catalog)
        return statement

    def _render(self, statement: Any) -> str:
        # Raise instead of silently dropping a construct the dialect cannot
        # express: the rendered SQL must mean what was validated.
        try:
            return statement.sql(dialect=self.dialect, comments=False, unsupported_level=ErrorLevel.RAISE)
        except UnsupportedError as exc:
            raise SQLGuardrailError(
                "The SQL uses a feature this data source cannot run safely. Please rephrase the question."
            ) from exc

    def validate_and_clamp(self, sql: str) -> GuardedSQL:
        statement = self._validated(sql)
        current_limit = _limit_value(statement.args.get("limit"))
        clamped = False
        # Unknown/negative/parameterized LIMITs cannot prove a bounded result set.
        if current_limit is None or current_limit > self.max_limit:
            statement.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
            effective_limit = self.max_limit
            clamped = True
        else:
            effective_limit = current_limit
        rendered = self._render(statement)
        # The rendered SQL is what the user approves and what runs. Re-parse
        # it until it is a fixed point (sqlglot may normalize once more, e.g.
        # keyword case), re-validating every pass, so approval can match it
        # byte-for-byte and the database never sees unvalidated text.
        for _ in range(3):
            again = self._render(self._validated(rendered))
            if again == rendered:
                return GuardedSQL(sql=rendered, limit=effective_limit, limit_clamped=clamped)
            rendered = again
        raise SQLGuardrailError("The SQL could not be normalized safely. Please rephrase the question.")

    def validate_exact(self, sql: str) -> GuardedSQL:
        """Re-validate approved SQL. It must already be in its guarded form."""

        guarded = self.validate_and_clamp(sql)
        if guarded.sql != sql:
            raise SQLGuardrailError(
                "The approved SQL no longer matches the current safety settings. Please ask the question again."
            )
        return guarded

    def validate(self, sql: str) -> str:
        return self.validate_and_clamp(sql).sql

    def requires_confirmation(self, sql: str) -> bool:
        """Return whether a safe query has joins or nested SELECTs."""

        statement = self._validated(sql)
        joins = sum(1 for node in statement.walk() if isinstance(node, exp.Join))
        nested_selects = sum(1 for node in statement.walk() if isinstance(node, exp.Select)) - 1
        return joins > 1 or nested_selects > 0


def validate_and_clamp_sql(
    sql: str, *, max_limit: int = 500, dialect: str | None = "sqlite", catalog: SchemaCatalog | None = None
) -> str:
    """Convenience API for the SQL-execution boundary."""

    return SQLGuardrails(max_limit=max_limit, dialect=dialect, catalog=catalog).validate(sql)


validate_sql = validate_and_clamp_sql
