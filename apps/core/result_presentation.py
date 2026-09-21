"""Deterministic, user-facing presentation of read-only query results."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from numbers import Real
import re
from typing import Any


@dataclass(frozen=True)
class ResultPresentation:
    """Plain-language text and small numeric highlights derived from result rows."""

    headline: str
    detail: str
    highlights: list[tuple[str, str]]
    breakdown_title: str | None = None
    category_column: str | None = None
    total: tuple[str, str] | None = None
    recommendations: list[str] = field(default_factory=list)


def humanize_column(name: str) -> str:
    """Convert a database-style column name into a label for a non-technical user."""

    return str(name).replace("_", " ").strip().title()


def format_result_value(value: Any) -> str:
    """Format values for display without guessing units such as currency."""

    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if isfinite(numeric):
            if numeric.is_integer():
                return f"{int(numeric):,}"
            return f"{numeric:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _category_breakdown_columns(
    question: str, columns: list[str], rows: list[dict[str, Any]]
) -> tuple[str, str] | None:
    """Find a simple category-plus-measure result that can be totaled safely."""

    if len(rows) < 2:
        return None
    if not re.search(r"\b(total|sum|average|mean|count|budget|revenue|profit|expense|spend)\b", question.lower()):
        return None
    category_columns = [
        column for column in columns
        if all(not isinstance(row.get(column), Real) or isinstance(row.get(column), bool) for row in rows)
    ]
    numeric_columns = [
        column for column in columns
        if all(isinstance(row.get(column), Real) and not isinstance(row.get(column), bool) for row in rows)
    ]
    if len(category_columns) != 1 or len(numeric_columns) != 1:
        return None
    return category_columns[0], numeric_columns[0]


def order_category_rows(
    question: str, rows: list[dict[str, Any]], category_column: str | None
) -> list[dict[str, Any]]:
    """Keep category rows in the order the user mentioned them when possible."""

    if not category_column:
        return rows
    question_lower = question.lower()

    def sort_key(indexed_row: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        original_index, row = indexed_row
        value = str(row.get(category_column, "")).strip().lower()
        position = question_lower.find(value) if value else -1
        return (position if position >= 0 else len(question_lower) + original_index, original_index)

    return [row for _, row in sorted(enumerate(rows), key=sort_key)]


def build_result_presentation(
    question: str, columns: list[str], rows: list[dict[str, Any]]
) -> ResultPresentation:
    """Describe exactly what the executed query returned, without model inference."""

    if not rows:
        return ResultPresentation(
            headline="No matching data was found.",
            detail="The validated read-only query completed successfully, but no rows matched the question.",
            highlights=[],
        )

    if len(rows) == 1:
        row = rows[0]
        numeric_columns = [
            column for column in columns if isinstance(row.get(column), Real) and not isinstance(row.get(column), bool)
        ]
        highlights = [(humanize_column(column), format_result_value(row[column])) for column in numeric_columns[:3]]
        if len(numeric_columns) == 1:
            column = numeric_columns[0]
            headline = f"{humanize_column(column)}: {format_result_value(row[column])}"
        else:
            headline = "One matching result was found."
        return ResultPresentation(
            headline=headline,
            detail="This answer is based on one result returned by the validated read-only query.",
            highlights=highlights,
        )

    breakdown = _category_breakdown_columns(question, columns, rows)
    if breakdown:
        category_column, value_column = breakdown
        total_value = sum(float(row[value_column]) for row in rows)
        category_label = humanize_column(category_column)
        value_label = humanize_column(value_column)
        return ResultPresentation(
            headline=f"{value_label} by {category_label}",
            detail=f"Each {category_label.lower()} is shown separately. The combined total appears after the breakdown.",
            highlights=[],
            breakdown_title=f"{value_label} by {category_label}",
            category_column=category_column,
            total=(f"Total {value_label}", format_result_value(total_value)),
            recommendations=[
                f"Which {category_label.lower()} has the highest {value_label.lower()}?",
                f"What share of the total {value_label.lower()} does each {category_label.lower()} represent?",
                f"Show {value_label.lower()} by {category_label.lower()} from highest to lowest.",
            ],
        )

    return ResultPresentation(
        headline=f"Found {len(rows):,} matching results.",
        detail="The detailed breakdown below contains every row returned by the validated read-only query.",
        highlights=[("Matching results", f"{len(rows):,}")],
    )


__all__ = ["ResultPresentation", "build_result_presentation", "format_result_value", "humanize_column", "order_category_rows"]
