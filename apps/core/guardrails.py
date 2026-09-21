"""AST-based read-only SQL guardrails for untrusted SQL proposals."""

from __future__ import annotations

from dataclasses import dataclass
import re
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


class DataQuestionScopeError(SQLGuardrailError):
    """Raised when a question is clearly outside the connected data scope."""


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


def _only_one_select(sql: str, dialect: str | None, source_table_names: set[str] | None = None) -> Any:
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
    table_nodes = [node for node in statement.walk() if isinstance(node, exp.Table)]
    if not table_nodes:
        raise SQLGuardrailError("The query must read from the uploaded workspace data; literal-only answers are not allowed.")
    if source_table_names:
        allowed_names = {name.lower() for name in source_table_names}
        referenced_names = {str(node.name).lower() for node in table_nodes}
        if not referenced_names.intersection(allowed_names):
            raise SQLGuardrailError("The query must reference a table from the uploaded workspace data.")
    if not any(
        isinstance(node, (exp.Column, exp.Star))
        for projection in statement.expressions
        for node in projection.walk()
    ):
        raise SQLGuardrailError("The query result must be derived from uploaded data, not a literal answer.")
    return statement


_QUESTION_TOKEN = re.compile(r"[a-z][a-z0-9_]{1,}")
_QUESTION_STOP_WORDS = {
    "about", "and", "are", "can", "data", "does", "for", "from", "have", "how", "into", "is", "list",
    "many", "much", "of", "or", "please", "show", "tell", "that", "the", "this", "what", "which", "who",
    "with", "would", "your",
}
_SCHEMA_TYPE_WORDS = {"bigint", "boolean", "date", "datetime", "decimal", "float", "integer", "numeric", "real", "text", "varchar"}
_GENERAL_KNOWLEDGE_PATTERN = re.compile(
    r"\b(prime minister|president|capital of|weather|latest news|celebrity|joke|riddle|horoscope)\b",
    flags=re.IGNORECASE,
)
_EXTERNAL_DATA_PATTERN = re.compile(
    r"\b(?:outside\s+(?:this\s+)?(?:uploaded\s+)?(?:workspace\s+)?data|"
    r"outside\s+this\s+uploaded|current\s+market\s+trends?|"
    r"market\s+trends?\s+outside|latest\s+market\s+trends?|"
    r"(?:from|on)\s+the\s+(?:web|internet))\b",
    flags=re.IGNORECASE,
)


def _schema_terms(schema: str) -> set[str]:
    """Return both database identifiers and their human-readable word parts."""

    identifiers = set(_QUESTION_TOKEN.findall(schema.lower())) - _SCHEMA_TYPE_WORDS
    return identifiers | {part for identifier in identifiers for part in identifier.split("_") if part}


def validate_data_question(question: str, schema: str) -> None:
    """Reject clearly unrelated questions before a model receives them."""

    if not isinstance(question, str) or not question.strip():
        raise DataQuestionScopeError("Enter a question about the uploaded data.")
    if not isinstance(schema, str) or not schema.strip():
        raise DataQuestionScopeError("The uploaded data schema is unavailable, so this question cannot be checked.")

    # Check this before matching schema words.  An out-of-scope prompt can
    # mention a valid table term such as "product" while still explicitly
    # demanding facts that are not present in the uploaded workspace.
    if _EXTERNAL_DATA_PATTERN.search(question):
        raise DataQuestionScopeError(
            "This assistant cannot use market trends or other information outside the uploaded data. "
            "Ask for an analysis based only on this workspace's tables and fields."
        )

    question_terms = set(_QUESTION_TOKEN.findall(question.lower())) - _QUESTION_STOP_WORDS
    schema_terms = _schema_terms(schema)
    if question_terms.intersection(schema_terms):
        return
    if _GENERAL_KNOWLEDGE_PATTERN.search(question):
        raise DataQuestionScopeError(
            "This assistant only answers questions grounded in the uploaded data. "
            "Ask about a table, field, record, or metric in this workspace."
        )
    raise DataQuestionScopeError(
        "This question does not appear related to the uploaded data. "
        "Ask about the tables, fields, records, or metrics in this workspace."
    )


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

    def validate_and_clamp(self, sql: str, *, source_table_names: set[str] | None = None) -> GuardedSQL:
        statement = _only_one_select(sql, self.dialect, source_table_names)
        current_limit = _limit_value(statement.args.get("limit"))
        # Unknown/negative/parameterized LIMITs cannot prove a bounded result set.
        if current_limit is None or current_limit > self.max_limit:
            statement.limit(self.max_limit, copy=False)
            effective_limit = self.max_limit
        else:
            effective_limit = current_limit
        return GuardedSQL(sql=statement.sql(dialect=self.dialect), limit=effective_limit)

    def validate(self, sql: str, *, source_table_names: set[str] | None = None) -> str:
        return self.validate_and_clamp(sql, source_table_names=source_table_names).sql

    def requires_confirmation(self, sql: str) -> bool:
        """Return whether a safe query has joins or nested SELECTs.

        This is an experience safeguard, not a reason to reject valid analysis:
        callers can require an additional explicit approval for more complex SQL.
        """

        statement = _only_one_select(sql, self.dialect)
        joins = sum(1 for node in statement.walk() if isinstance(node, exp.Join))
        nested_selects = sum(1 for node in statement.walk() if isinstance(node, exp.Select)) - 1
        return joins > 1 or nested_selects > 0


def validate_and_clamp_sql(
    sql: str, *, max_limit: int = 500, dialect: str | None = "sqlite"
) -> str:
    """Convenience API for the SQL-execution boundary."""

    return SQLGuardrails(max_limit=max_limit, dialect=dialect).validate(sql)


validate_sql = validate_and_clamp_sql
