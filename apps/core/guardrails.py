"""AST-based read-only SQL guardrails for untrusted SQL proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from sqlglot import exp, parse
    from sqlglot.errors import ParseError
except ImportError:  # pragma: no cover - only reached without installed dependencies
    exp = None  # type: ignore[assignment]
    parse = None  # type: ignore[assignment]
    ParseError = Exception


class SQLGuardrailError(ValueError):
    """Raised when untrusted SQL fails a server-side safety policy."""


@dataclass(frozen=True)
class GuardedSQL:
    sql: str
    limit: int


# A SELECT root is necessary but insufficient: PostgreSQL has data-changing CTEs
# and SELECT INTO writes a table. Reject these nodes anywhere in the AST.
_DISALLOWED_AST_NODES = (
    "Alter", "Analyze", "Attach", "Cache", "Command", "Commit", "Copy", "Create",
    "Delete", "Detach", "Drop", "Execute", "Grant", "Insert", "Into", "LoadData",
    "Lock", "Merge", "Pragma", "Rename", "Revoke", "Rollback", "Set", "Transaction",
    "TruncateTable", "Uncache", "Update", "Use", "Vacuum",
)


def _require_sqlglot() -> None:
    if parse is None or exp is None:
        raise RuntimeError(
            "sqlglot is required for SQL guardrails. Install dependencies with `pip install -r requirements.txt`."
        )


def _only_one_select(sql: str, dialect: str | None) -> Any:
    if not isinstance(sql, str) or not sql.strip():
        raise SQLGuardrailError("SQL must be a non-empty string.")
    _require_sqlglot()
    try:
        statements = parse(sql, read=dialect)
    except ParseError as exc:
        raise SQLGuardrailError("SQL could not be parsed.") from exc
    if len(statements) != 1:
        raise SQLGuardrailError("Exactly one SQL statement is allowed.")

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise SQLGuardrailError("Only a single SELECT statement is allowed.")
    blocked_types = tuple(
        node_type for name in _DISALLOWED_AST_NODES if (node_type := getattr(exp, name, None)) is not None
    )
    if blocked_types and any(isinstance(node, blocked_types) for node in statement.walk()):
        raise SQLGuardrailError("Only read-only SELECT SQL is allowed.")
    return statement


def _limit_value(limit_expression: Any) -> int | None:
    """Return a non-negative literal LIMIT, or ``None`` for non-literals."""

    if limit_expression is None:
        return None
    expression = limit_expression.args.get("expression")
    if expression is None:
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

    def __post_init__(self) -> None:
        if isinstance(self.max_limit, bool) or not isinstance(self.max_limit, int) or self.max_limit <= 0:
            raise ValueError("max_limit must be a positive integer")

    def validate_and_clamp(self, sql: str) -> GuardedSQL:
        statement = _only_one_select(sql, self.dialect)
        current_limit = _limit_value(statement.args.get("limit"))
        # Unknown/negative/parameterized LIMITs cannot prove a bounded result set.
        if current_limit is None or current_limit > self.max_limit:
            statement.limit(self.max_limit, copy=False)
            effective_limit = self.max_limit
        else:
            effective_limit = current_limit
        return GuardedSQL(sql=statement.sql(dialect=self.dialect), limit=effective_limit)

    def validate(self, sql: str) -> str:
        return self.validate_and_clamp(sql).sql


def validate_and_clamp_sql(
    sql: str, *, max_limit: int = 500, dialect: str | None = "sqlite"
) -> str:
    """Convenience API for the SQL-execution boundary."""

    return SQLGuardrails(max_limit=max_limit, dialect=dialect).validate(sql)


validate_sql = validate_and_clamp_sql
