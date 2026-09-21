#!/usr/bin/env python3
"""Standalone guarded Text-to-SQL test bench for locally trained MLX adapters.

This program intentionally does not import or modify Puchoo.ai.  It accepts a
local SQLite database and a natural-language question, introspects its schema,
asks a local adapter for one SQL query, validates it, and prints real rows.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler


SYSTEM_PROMPT = """You write exactly one read-only SQLite SELECT statement.
Use only the supplied schema. Return SQL only: no explanation, Markdown, or
code fences. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA,
ATTACH, DETACH, VACUUM, or transaction commands."""

BLOCKED_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|PRAGMA|ATTACH|DETACH|VACUUM|"
    r"REINDEX|ANALYZE|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)


@dataclass
class Attempt:
    number: int
    sql: str
    accepted: bool
    feedback: list[str]


def introspect_schema(connection: sqlite3.Connection) -> str:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    if not tables:
        raise ValueError("The supplied SQLite database has no user tables.")

    lines = []
    for table in tables:
        columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        fields = ", ".join(f"{column[1]} {column[2]}" for column in columns)
        lines.append(f"{table}({fields})")
    return "\n".join(lines)


def clean_sql(text: str) -> str:
    text = re.sub(r"^\s*```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "").strip()
    # Some chat templates surface their end-of-message marker in generated
    # text. It is not SQL and must never reach SQLite.
    text = re.sub(r"<\|[^>]+\|>", "", text)
    text = text.replace("</s>", "").strip()
    return text.rstrip(";").strip()


def semantic_checks(question: str, sql: str) -> list[str]:
    """Small, explainable checks for high-risk business-language mistakes.

    These are deliberately conservative. A failure asks the local model to
    repair its candidate; it never silently rewrites a query.
    """

    errors: list[str] = []
    question_lower = question.lower()
    sql_lower = sql.lower()

    if re.search(r"\b(average|mean)\b", question_lower):
        if "avg(" not in sql_lower:
            errors.append("The question asks for an average, but SQL has no AVG(...).")
        if "having" not in sql_lower:
            errors.append("An average-based filter must use HAVING with AVG(...), not WHERE.")
        having_part = sql_lower.split("having", 1)[1] if "having" in sql_lower else ""
        if "avg(" not in having_part:
            errors.append("The HAVING clause must compare AVG(...) to the requested limit.")

    # "Unpaid invoices" means an invoice status; it is not the same as the
    # education/finance calculation called "unpaid fees" or "unpaid balance".
    if re.search(r"\bunpaid\s+(?:fee|fees|amount|balance)\b", question_lower):
        # A result alias is acceptable only if the actual subtraction is also
        # present somewhere in the SQL.
        if not re.search(
            r"(?:\b\w+\.)?amount_due\b\s*-\s*(?:\b\w+\.)?amount_paid\b",
            sql_lower,
        ):
            errors.append(
                "Unpaid amount must be calculated as amount_due - amount_paid; "
                "do not use amount_due alone."
            )

    preaggregated_fee_subquery = re.search(
        r"join\s*\(\s*select\b.*?sum\s*\(\s*amount_due\s*-\s*amount_paid\s*\)"
        r".*?from\s+fees\b.*?group\s+by\s+student_id.*?\)\s+\w+",
        sql_lower,
        re.DOTALL,
    )

    if preaggregated_fee_subquery:
        if "f.amount_due" in sql_lower or "f.amount_paid" in sql_lower:
            errors.append(
                "The fee subquery exposes only f.student_id and f.unpaid_fees. "
                "After joining it, replace every f.amount_due/f.amount_paid reference "
                "with f.unpaid_fees."
            )
        if re.search(r"sum\s*\(\s*f\.unpaid_fees\s*\)", sql_lower):
            errors.append(
                "f.unpaid_fees is already pre-aggregated per student. Select and filter "
                "f.unpaid_fees directly; do not SUM(f.unpaid_fees) after joining grades."
            )

    if (
        re.search(r"\b(average|mean)\b", question_lower)
        and re.search(r"\bunpaid\s+(?:fee|fees|amount|balance)\b", question_lower)
        and "join grades" in sql_lower
        and re.search(
            r"sum\s*\(\s*(?:\b\w+\.)?amount_due\b\s*-\s*(?:\b\w+\.)?amount_paid\b",
            sql_lower,
        )
        and not preaggregated_fee_subquery
    ):
        errors.append(
            "Do not SUM unpaid fees directly after joining grades: grade rows can "
            "duplicate each fee. Pre-aggregate fees per student before that join, "
            "or use a non-aggregate fee expression when there is one fee row."
        )

    if (
        ("active enrollment" in question_lower or "enrollment status" in question_lower)
        and "enrollment_status" not in sql_lower
    ):
        errors.append(
            "The question requires active enrollments, so filter enrollment_status = 'active'."
        )

    if re.search(r"\bunpaid\s+or\s+partial\s+invoices?\b", question_lower):
        has_both_statuses = (
            "payment_status" in sql_lower
            and re.search(r"['\"]unpaid['\"]", sql_lower)
            and re.search(r"['\"]partial['\"]", sql_lower)
        )
        if not has_both_statuses:
            errors.append(
                "The question asks for unpaid OR partial invoices. Filter payment_status "
                "to both literal values 'unpaid' and 'partial' (for example with IN), "
                "not only one status."
            )
    elif re.search(r"\bpartial\s+invoices?\b", question_lower):
        if "payment_status" not in sql_lower or not re.search(r"['\"]partial['\"]", sql_lower):
            errors.append(
                "The question asks for partial invoices. Filter the invoice payment_status "
                "to the literal value 'partial'; do not replace that condition with an amount filter."
            )

    return errors


def safety_and_syntax_checks(connection: sqlite3.Connection, sql: str) -> list[str]:
    errors: list[str] = []
    if not re.match(r"^SELECT\b", sql, re.IGNORECASE):
        errors.append("Only a single SQL SELECT statement is permitted.")
        return errors
    if BLOCKED_WORDS.search(sql):
        errors.append("The query contains a forbidden write or administration keyword.")
    if ";" in sql:
        errors.append("Only one SQL statement is permitted; remove extra semicolons.")
    if errors:
        return errors

    try:
        connection.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
    except sqlite3.Error as exc:
        errors.append(f"SQLite syntax/schema validation failed: {exc}")
    return errors


def render_table(columns: Iterable[str], rows: list[tuple]) -> str:
    columns = [str(column) for column in columns]
    values = [["" if value is None else str(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]
    for row in values:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def line(values_: list[str]) -> str:
        return "| " + " | ".join(
            value.ljust(widths[index]) for index, value in enumerate(values_)
        ) + " |"

    divider = "| " + " | ".join("-" * width for width in widths) + " |"
    output = [line(columns), divider]
    output.extend(line(row) for row in values)
    return "\n".join(output)


def generate_sql(
    model,
    tokenizer,
    schema: str,
    question: str,
    feedback: list[str] | None,
    previous_sql: str | None,
) -> str:
    user_content = f"Schema:\n{schema}\n\nQuestion:\n{question}"
    if feedback:
        user_content += (
            "\n\nThe previous SQL was rejected:\n```sql\n"
            + (previous_sql or "")
            + "\n```\n\nCorrect every issue below and return one replacement SELECT "
            "statement only:\n- "
            + "\n- ".join(feedback)
        )

    prompt = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
    return clean_sql(
        generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=350,
            sampler=make_sampler(temp=0.0),
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to a local SQLite database")
    parser.add_argument(
        "--adapter",
        default=None,
        help="Optional path to an MLX LoRA adapter directory",
    )
    parser.add_argument(
        "--model",
        default="mlx-community/Qwen2.5-3B-Instruct-4bit",
        help="Base MLX model name or path",
    )
    parser.add_argument("--question", required=True, help="Natural-language data question")
    parser.add_argument("--max-attempts", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument(
        "--report-dir",
        default="model_training/evaluation/reports",
        help="Directory for JSON evidence reports",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    schema = introspect_schema(connection)
    print("DATABASE SCHEMA:\n")
    print(schema)

    model, tokenizer = load(args.model, adapter_path=args.adapter)
    attempts: list[Attempt] = []
    feedback: list[str] | None = None
    previous_sql: str | None = None

    accepted_sql: str | None = None
    result_rows: list[tuple] = []
    result_columns: list[str] = []

    for number in range(1, args.max_attempts + 1):
        sql = generate_sql(
            model,
            tokenizer,
            schema,
            args.question,
            feedback,
            previous_sql,
        )
        errors = safety_and_syntax_checks(connection, sql)
        # Semantic feedback is useful even if SQLite has already found a
        # syntax error; otherwise a repair attempt may fix only one of two
        # independent problems.
        if re.match(r"^SELECT\b", sql, re.IGNORECASE) and not BLOCKED_WORDS.search(sql):
            errors.extend(semantic_checks(args.question, sql))

        accepted = not errors
        attempts.append(Attempt(number, sql, accepted, errors))
        print(f"\nATTEMPT {number} SQL:\n\n{sql}\n")

        if accepted:
            cursor = connection.execute(sql)
            result_rows = cursor.fetchall()
            result_columns = [column[0] for column in cursor.description]
            accepted_sql = sql
            break

        print("REJECTED:")
        for error in errors:
            print(f"- {error}")
        feedback = errors
        previous_sql = sql

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "database": str(db_path),
        "question": args.question,
        "adapter": args.adapter,
        "schema": schema,
        "attempts": [asdict(attempt) for attempt in attempts],
        "accepted_sql": accepted_sql,
        "row_count": len(result_rows),
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"sql_bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if accepted_sql is None:
        print("\nRESULT: BLOCKED — no safe, executable, semantically acceptable SQL was produced.")
        print(f"Evidence report: {report_path}")
        return 1

    print(f"\nANSWER: Found {len(result_rows)} matching row(s).")
    print("\nRESULT TABLE:\n")
    print(render_table(result_columns, result_rows) if result_rows else "No matching rows.")
    print(f"\nRESULT: PASS — query was validated before execution.")
    print(f"Evidence report: {report_path}")
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
