"""Plan and route complex natural-language analytics questions.

The module is intentionally independent from SQL execution.  It classifies a
question, validates the local model's JSON plan, and selects a bounded subset
of the supplied schema.  Raw database rows are never included.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from apps.core.semantic_layer import parse_schema


DEFAULT_MAX_RELEVANT_TABLES = 6
DEFAULT_SCHEMA_CONTEXT_CHARS = 12_000


@dataclass(frozen=True)
class ComplexityDecision:
    route: str
    score: int
    reasons: tuple[str, ...]


@dataclass
class StructuredQueryPlan:
    normalized_question: str
    relevant_tables: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    time_range: str | None = None
    group_by: list[str] = field(default_factory=list)
    ranking: dict[str, Any] | None = None
    joins: list[dict[str, str]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PlannerClient(Protocol):
    def generate_plan(self, *, schema: str, question: str) -> str: ...


class QueryPlanError(ValueError):
    """Raised when the planner response violates the strict contract."""


def _schema_catalog(schema: str, question: str) -> str:
    """Build a bounded metadata-only catalog for the planning call."""

    tables = parse_schema(schema)
    tokens = set(re.findall(r"[a-z][a-z0-9_]+", question.lower()))
    ranked = sorted(
        tables,
        key=lambda table: len(tokens & (set(table.name.lower().split("_")) | {c.lower() for c in table.columns})),
        reverse=True,
    )
    max_chars = _configured_int("LOCAL_SQL_SCHEMA_MAX_CHARS", DEFAULT_SCHEMA_CONTEXT_CHARS, 1_000, 50_000)
    blocks: list[str] = []
    for table in ranked:
        # Planner catalog intentionally excludes representative categorical values.
        block = "\n".join(line for line in table.block.splitlines() if not line.startswith("Values for "))
        candidate = "\n\n".join(blocks + [block])
        if len(candidate) > max_chars:
            continue
        blocks.append(block)
    if not blocks:
        raise QueryPlanError("No schema metadata fits within the configured planner context limit.")
    return "\n\n".join(blocks)


_COMPLEX_PATTERNS: tuple[tuple[str, str, int], ...] = (
    ("ranking", r"\b(top|bottom|highest|lowest|rank|best|worst)\b", 2),
    ("comparison", r"\b(compare|versus|vs\.?|difference|change|growth|declin|previous|prior)\w*\b", 2),
    ("time", r"\b(rolling|fiscal|quarter|year[- ]over[- ]year|month[- ]over[- ]month|between|last\s+\d+)\b", 2),
    ("ratio", r"\b(ratio|rate|percentage|percent|share|conversion|margin)\b", 2),
    ("exclusion", r"\b(except|exclude|excluding|without|never|not\s+in)\b", 2),
    ("nested", r"\b(above|below|greater|less)\b.*\b(average|total|median)\b", 2),
    ("multi_part", r"\b(and|then|also|while)\b", 1),
)


def classify_complexity(question: str, schema: str = "") -> ComplexityDecision:
    """Route obvious simple requests quickly and plan difficult requests."""

    q = " ".join(question.lower().split())
    score = 0
    reasons: list[str] = []
    word_count = len(q.split())
    if word_count >= 24:
        score += 3
        reasons.append("long_wording")
    elif word_count >= 15:
        score += 2
        reasons.append("long_wording")
    for reason, pattern, weight in _COMPLEX_PATTERNS:
        if re.search(pattern, q):
            score += weight
            reasons.append(reason)
    metric_terms = re.findall(
        r"\b(revenue|sales|quantity|count|average|total|attendance|marks?|fees?|balance|profit|cost|budget)\b",
        q,
    )
    if len(set(metric_terms)) >= 2:
        score += 3
        reasons.append("multiple_metrics")
    table_mentions = 0
    for table in parse_schema(schema):
        tokens = [token for token in table.name.lower().split("_") if len(token) > 2]
        if any(re.search(rf"\b{re.escape(token.rstrip('s'))}s?\b", q) for token in tokens):
            table_mentions += 1
    if table_mentions >= 2:
        score += 3
        reasons.append("multiple_tables")
    if re.search(r"\b(doing well|performing well|recent|significant|healthy|valuable|successful)\b", q):
        score += 3
        reasons.append("ambiguity")
    return ComplexityDecision("planned" if score >= 3 else "simple", score, tuple(dict.fromkeys(reasons)))


PLANNER_SYSTEM_PROMPT = """You are a query planner for a read-only SQLite analytics application.
Return exactly one JSON object and no SQL, Markdown, or commentary. Preserve every explicit user constraint.
Use only tables and columns present in the supplied schema. This is an autonomous, single-prompt workflow:
never ask the user a follow-up question. Resolve ambiguity using the closest explicit schema field and record
every resolution in assumptions. Prefer stored categorical status fields over inferred definitions (for example,
loan_status='Overdue' defines overdue when that value exists). For relative dates use the current date. Use
conventional calendar periods and schema-backed averages when no business definition is supplied. Never invent
tables, columns, or unavailable facts. Always set needs_clarification false and clarification_question null.
The object must contain: normalized_question, relevant_tables, metrics, filters, time_range, group_by,
ranking, joins, assumptions, needs_clarification, clarification_question."""


def build_planner_prompt(question: str, schema: str) -> str:
    payload = json.dumps({"original_question": question.strip(), "schema": schema.strip()}, ensure_ascii=False)
    return PLANNER_SYSTEM_PROMPT + "\n<planner_request>" + payload + "</planner_request>"


def parse_plan_json(content: str, *, schema: str, original_question: str) -> StructuredQueryPlan:
    """Validate planner JSON and reject unknown tables or incomplete contracts."""

    cleaned = re.sub(r"<\|[^>]+\|>", "", (content or "").strip()).replace("</s>", "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.IGNORECASE | re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        raise QueryPlanError("The local planner returned invalid JSON. Please rephrase the question.") from exc
    if not isinstance(payload, dict):
        raise QueryPlanError("The local planner did not return a JSON object.")

    # Accept the singular names shown in the design document, then normalize to
    # the app's list-based contract before strict validation.
    if "metrics" not in payload and "metric" in payload:
        metric = payload.pop("metric")
        payload["metrics"] = metric if isinstance(metric, list) else ([str(metric)] if metric else [])
    if "time_range" not in payload and "period" in payload:
        payload["time_range"] = payload.pop("period")

    required = {
        "normalized_question", "relevant_tables", "metrics", "filters", "time_range",
        "group_by", "ranking", "joins", "assumptions", "needs_clarification",
    }
    if missing := sorted(required - payload.keys()):
        raise QueryPlanError("The local planner response is missing: " + ", ".join(missing) + ".")
    list_fields = ("relevant_tables", "metrics", "filters", "group_by", "joins", "assumptions")
    if any(not isinstance(payload.get(name), list) for name in list_fields):
        raise QueryPlanError("The local planner returned invalid list fields.")
    if not isinstance(payload.get("needs_clarification"), bool):
        raise QueryPlanError("The local planner returned an invalid clarification flag.")
    if not isinstance(payload.get("normalized_question"), str) or not payload["normalized_question"].strip():
        raise QueryPlanError("The local planner returned an empty normalized question.")

    known_tables = {table.name for table in parse_schema(schema)}
    relevant_tables = list(dict.fromkeys(str(name) for name in payload["relevant_tables"]))
    unknown = sorted(set(relevant_tables) - known_tables)
    if unknown:
        raise QueryPlanError("The local planner selected unknown tables: " + ", ".join(unknown) + ".")
    needs_clarification = payload["needs_clarification"]
    clarification_question = payload.get("clarification_question")
    if needs_clarification and (not isinstance(clarification_question, str) or not clarification_question.strip()):
        raise QueryPlanError("The local planner requested clarification without a question.")

    return StructuredQueryPlan(
        normalized_question=payload["normalized_question"].strip(),
        relevant_tables=relevant_tables,
        metrics=[str(value) for value in payload["metrics"]],
        filters=[str(value) for value in payload["filters"]],
        time_range=str(payload["time_range"]) if payload["time_range"] is not None else None,
        group_by=[str(value) for value in payload["group_by"]],
        ranking=payload["ranking"] if isinstance(payload["ranking"], dict) else None,
        joins=[dict(value) for value in payload["joins"] if isinstance(value, dict)],
        assumptions=[str(value) for value in payload["assumptions"]],
        needs_clarification=needs_clarification,
        clarification_question=clarification_question.strip() if isinstance(clarification_question, str) else None,
    )


def plan_complex_query(client: PlannerClient, *, schema: str, question: str) -> StructuredQueryPlan:
    catalog = _schema_catalog(schema, question)
    return parse_plan_json(client.generate_plan(schema=catalog, question=question), schema=schema, original_question=question)


def _configured_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(lower, min(value, upper))


def select_plan_schema(schema: str, plan: StructuredQueryPlan) -> tuple[str, list[str]]:
    """Return only planned schema blocks within table and character limits."""

    tables = parse_schema(schema)
    max_tables = _configured_int("LOCAL_SQL_SCHEMA_MAX_TABLES", DEFAULT_MAX_RELEVANT_TABLES, 1, 12)
    max_chars = _configured_int("LOCAL_SQL_SCHEMA_MAX_CHARS", DEFAULT_SCHEMA_CONTEXT_CHARS, 1_000, 50_000)
    selected_names = plan.relevant_tables[:max_tables]
    if not selected_names:
        # Safe lexical fallback: choose the closest table blocks, never the full schema.
        tokens = set(re.findall(r"[a-z][a-z0-9_]+", plan.normalized_question.lower()))
        ranked = sorted(
            tables,
            key=lambda table: len(tokens & (set(table.name.lower().split("_")) | {c.lower() for c in table.columns})),
            reverse=True,
        )
        selected_names = [table.name for table in ranked[:max_tables]]
    blocks: list[str] = []
    actual_names: list[str] = []
    for table in tables:
        if table.name not in selected_names:
            continue
        candidate = "\n\n".join(blocks + [table.block])
        if len(candidate) > max_chars:
            continue
        blocks.append(table.block)
        actual_names.append(table.name)
    if not blocks:
        raise QueryPlanError("No relevant schema fits within the configured context limit.")
    return "\n\n".join(blocks), actual_names


def build_plan_sql_request(original_question: str, plan: StructuredQueryPlan) -> str:
    """Serialize the authoritative plan for the SQL generation call."""

    return (
        "Original question (preserve every explicit constraint):\n"
        + original_question.strip()
        + "\n\nValidated structured plan (authoritative):\n"
        + json.dumps(plan.as_dict(), ensure_ascii=False, separators=(",", ":"))
        + "\n\nGenerate SQLite SQL only. Do not add constraints absent from the question or plan."
    )


def plan_constraint_feedback(plan: StructuredQueryPlan, sql: str) -> list[str]:
    """Catch obvious loss of planned tables, metrics, grouping, or ranking."""

    sql_lower = sql.lower()
    feedback: list[str] = []
    referenced = set(re.findall(r'(?:from|join)\s+["`\[]?([a-z_][\w]*)', sql_lower))
    ctes = set(re.findall(r'(?:with|,)\s*([a-z_][\w]*)\s+as\s*\(', sql_lower))
    missing_tables = [name for name in plan.relevant_tables if name.lower() not in referenced]
    if missing_tables and plan.joins:
        feedback.append("Use every planned table required by the joins: " + ", ".join(missing_tables) + ".")
    unexpected = sorted(referenced - {name.lower() for name in plan.relevant_tables} - ctes)
    if unexpected:
        feedback.append("Remove tables outside the structured plan: " + ", ".join(unexpected) + ".")
    for metric in plan.metrics:
        tokens = [token for token in re.findall(r"[a-z_][a-z0-9_]*", metric.lower()) if len(token) > 2]
        if tokens and not any(token in sql_lower for token in tokens):
            feedback.append(f"Preserve the planned metric: {metric}.")
    if plan.group_by and "group by" not in sql_lower:
        feedback.append("The structured plan requires grouping; add the planned GROUP BY dimensions.")
    if plan.ranking:
        if "order by" not in sql_lower:
            feedback.append("The structured plan requires ranking; add ORDER BY.")
        has_partitioned_top_n = bool(
            re.search(r"(?:row_number|rank|dense_rank)\s*\(\s*\)\s*over", sql_lower)
            and re.search(r"\b(?:rn|rank|row_num|row_number)\b\s*<=?\s*\d+", sql_lower)
        )
        if plan.ranking.get("limit") and "limit" not in sql_lower and not has_partitioned_top_n:
            feedback.append("The structured plan requires a ranking limit; add LIMIT.")
    return feedback


__all__ = [
    "ComplexityDecision", "QueryPlanError", "StructuredQueryPlan", "build_plan_sql_request",
    "build_planner_prompt", "classify_complexity", "parse_plan_json", "plan_complex_query",
    "plan_constraint_feedback", "select_plan_schema",
]
