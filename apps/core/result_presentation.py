"""Deterministic, user-facing presentation of read-only query results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Any


@dataclass(frozen=True)
class ResultPresentation:
    """Plain-language text and small numeric highlights derived from result rows."""

    headline: str
    detail: str
    highlights: list[tuple[str, str]]


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

    return ResultPresentation(
        headline=f"Found {len(rows):,} matching results.",
        detail="The detailed breakdown below contains every row returned by the validated read-only query.",
        highlights=[("Matching results", f"{len(rows):,}")],
    )


__all__ = ["ResultPresentation", "build_result_presentation", "format_result_value", "humanize_column"]
