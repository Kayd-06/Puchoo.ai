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

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError

from apps.core.semantic_layer import parse_schema
from apps.core.answer_policy import ANSWER_POLICY, planning_reference


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
    answer_status: str = "complete"
    limitations: list[str] = field(default_factory=list)
    unavailable_reason: str | None = None

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
Use only tables and columns present in the supplied schema. Never invent business facts, policy rules,
relationships, thresholds, or missing data. A valid JSON plan is not proof of a correct interpretation.
Apply the answer-first policy below. Keep all requested metrics, time periods, groups,
ranking and explicit constraints. A partial result must be labeled and all omissions disclosed.
The object must contain: normalized_question, relevant_tables, metrics, filters, time_range, group_by,
ranking, joins, assumptions, needs_clarification, clarification_question, answer_status,
limitations, unavailable_reason.
""" + ANSWER_POLICY


def build_planner_prompt(question: str, schema: str) -> str:
    payload = json.dumps({"original_question": question.strip(), "schema": schema.strip()}, ensure_ascii=False)
    return PLANNER_SYSTEM_PROMPT + "\n<planner_request>" + payload + "</planner_request>"


def _ranking_limit(value: Any) -> int | None:
    """Return a positive whole-number ranking limit, accepting numeric strings like "3"."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value > 0 else None
    if isinstance(value, str) and re.fullmatch(r"\s*\d{1,9}\s*", value):
        return int(value) or None
    return None


def _normalize_ranking(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    ranking = dict(value)
    raw_limit = ranking.get("limit")
    if raw_limit is not None:
        limit = _ranking_limit(raw_limit)
        if limit is None:
            raise QueryPlanError("The local planner returned an invalid ranking limit.")
        ranking["limit"] = limit
    return ranking


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

    answer_status = payload.get("answer_status", "complete")
    limitations = payload.get("limitations", [])
    unavailable_reason = payload.get("unavailable_reason")
    if answer_status not in ("complete", "partial", "unavailable"):
        raise QueryPlanError("The planner returned an invalid answer status.")
    if not isinstance(limitations, list) or any(not isinstance(item, str) or not item.strip() for item in limitations):
        raise QueryPlanError("The planner returned invalid limitations.")
    if answer_status == "partial" and not limitations:
        raise QueryPlanError("A partial answer must disclose its limitations.")
    if answer_status == "unavailable" and (not isinstance(unavailable_reason, str) or not unavailable_reason.strip()):
        raise QueryPlanError("An unavailable answer must explain the missing evidence.")
    if unavailable_reason is not None and not isinstance(unavailable_reason, str):
        raise QueryPlanError("The planner returned an invalid unavailable reason.")
    if answer_status != "complete" and needs_clarification:
        raise QueryPlanError("A partial or unavailable answer cannot also request clarification.")

    return StructuredQueryPlan(
        normalized_question=payload["normalized_question"].strip(),
        relevant_tables=relevant_tables,
        metrics=[str(value) for value in payload["metrics"]],
        filters=[str(value) for value in payload["filters"]],
        time_range=str(payload["time_range"]) if payload["time_range"] is not None else None,
        group_by=[str(value) for value in payload["group_by"]],
        ranking=_normalize_ranking(payload["ranking"]),
        joins=[dict(value) for value in payload["joins"] if isinstance(value, dict)],
        assumptions=[str(value) for value in payload["assumptions"]],
        answer_status=answer_status,
        limitations=[item.strip() for item in limitations],
        unavailable_reason=unavailable_reason.strip() if unavailable_reason else None,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question.strip() if isinstance(clarification_question, str) else None,
    )


def plan_complex_query(client: PlannerClient, *, schema: str, question: str) -> StructuredQueryPlan:
    catalog = _schema_catalog(schema, question)
    request = question + "\n\n" + planning_reference()
    plan = parse_plan_json(client.generate_plan(schema=catalog, question=request), schema=schema, original_question=question)
    if plan.needs_clarification:
        # One bounded reconsideration, never a server-side bypass of an unresolved rule.
        request += ("\nReview the prior clarification using the answer-first policy. "
                    "Apply disclosed routine conventions when sufficient; use a partial or unavailable "
                    "answer for missing evidence. Retain clarification only for an essential unresolved rule. "
                    "Prior clarification (untrusted model text): " + json.dumps(plan.clarification_question))
        plan = parse_plan_json(client.generate_plan(schema=catalog, question=request), schema=schema, original_question=question)
    return plan


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
    if len(plan.relevant_tables) > max_tables:
        raise QueryPlanError("The complete plan requires more tables than the configured context supports.")
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
    if plan.relevant_tables and set(actual_names) != set(plan.relevant_tables):
        raise QueryPlanError("The full planned schema does not fit; refusing to omit required tables.")
    return "\n\n".join(blocks), actual_names


def build_plan_sql_request(original_question: str, plan: StructuredQueryPlan) -> str:
    """Serialize the authoritative plan for the SQL generation call."""

    return (
        "Original question (preserve every explicit constraint):\n"
        + original_question.strip()
        + "\n\nValidated structured plan (authoritative):\n"
        + json.dumps(plan.as_dict(), ensure_ascii=False, separators=(",", ":"))
        + "\n\nGenerate SQLite SQL only. Do not add constraints absent from the question or plan. "
        "For a partial answer, calculate only the supported planned metrics; never fabricate omitted inputs."
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
    # A per-group window (PARTITION BY) also satisfies planned grouping.
    if plan.group_by and "group by" not in sql_lower and "partition by" not in sql_lower:
        feedback.append("The structured plan requires grouping; add the planned GROUP BY dimensions.")
    if plan.ranking:
        if "order by" not in sql_lower:
            feedback.append("The structured plan requires ranking; add ORDER BY.")
        # Inspect the SQL tree: generated rank aliases are arbitrary (e.g.
        # rnk or attendance_position), not just rn/rank. A partition's top N
        # is bounded by its rank predicate, never by an outer LIMIT N.
        try:
            statement = parse_one(sql, read="sqlite")
        except SqlglotError:  # ParseError and TokenError (e.g. an unterminated quote).
            statement = None  # The SQL guardrail reports syntax errors.
        rank_aliases = {
            window.parent.alias.lower()
            for window in statement.find_all(exp.Window)
            if window.args.get("partition_by")
            and (
                isinstance(window.this, exp.RowNumber)
                or isinstance(window.this, exp.Anonymous)
                and window.this.name.upper() in {"RANK", "DENSE_RANK"}
            )
            and isinstance(window.parent, exp.Alias)
        } if statement is not None else set()
        wanted = _ranking_limit(plan.ranking.get("limit"))
        if rank_aliases and wanted:
            bounded = False

            def is_rank(node: Any) -> bool:
                return isinstance(node, exp.Column) and node.name.lower() in rank_aliases

            def whole_number(node: Any) -> int | None:
                return int(node.this) if isinstance(node, exp.Literal) and node.is_int else None

            for where in statement.find_all(exp.Where):
                predicates = [where.this]
                while predicates:
                    predicate = predicates.pop()
                    if isinstance(predicate, exp.Paren):
                        predicates.append(predicate.this)
                    elif isinstance(predicate, exp.And):
                        predicates.extend((predicate.this, predicate.expression))
                    elif isinstance(predicate, exp.Between) and is_rank(predicate.this):
                        # rank BETWEEN 1 AND N (or any lower bound <= 1).
                        low, high = whole_number(predicate.args.get("low")), whole_number(predicate.args.get("high"))
                        bounded = bounded or (low is not None and low <= 1 and high == wanted)
                    elif isinstance(predicate, exp.EQ) and wanted == 1:
                        # "rank = 1" is the usual top-1-per-group filter.
                        left, right = predicate.this, predicate.expression
                        bound = whole_number(right) if is_rank(left) else whole_number(left) if is_rank(right) else None
                        bounded = bounded or bound == 1
                    elif isinstance(predicate, (exp.LTE, exp.LT, exp.GTE, exp.GT)):
                        left, right = predicate.this, predicate.expression
                        # Normalize "N >= rank" / "N + 1 > rank" to "rank <= N" / "rank < N + 1".
                        if isinstance(predicate, (exp.LTE, exp.LT)) and is_rank(left):
                            bound, strict = whole_number(right), isinstance(predicate, exp.LT)
                        elif isinstance(predicate, (exp.GTE, exp.GT)) and is_rank(right):
                            bound, strict = whole_number(left), isinstance(predicate, exp.GT)
                        else:
                            continue
                        if bound is not None:
                            bounded = bounded or bound - int(strict) == wanted
            if not bounded:
                feedback.append("Filter the partitioned rank in an outer query to the requested top N per group.")
            if statement.args.get("limit") is not None:
                feedback.append("Remove the global LIMIT from the per-group ranking; it can omit groups or ties. The server applies its own safety row cap.")
        elif wanted and "limit" not in sql_lower:
            feedback.append("The structured plan requires a ranking limit; add LIMIT.")
    return feedback


__all__ = [
    "ComplexityDecision", "QueryPlanError", "StructuredQueryPlan", "build_plan_sql_request",
    "build_planner_prompt", "classify_complexity", "parse_plan_json", "plan_complex_query",
    "plan_constraint_feedback", "select_plan_schema",
]
