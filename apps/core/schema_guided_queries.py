"""Small, deterministic query routes for unambiguous analytics requests.

These routes are deliberately narrow.  They recognise common business
questions, inspect the uploaded schema for the required relationship, and
still pass the resulting SQL through the normal read-only executor.  They are
used before asking a smaller local model to reason over a wide schema.
"""

from __future__ import annotations

import re

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError


_RANK_WORDS = re.compile(
    r"\b(highest|top|best|most|lowest|least|worst|minimum)\b", flags=re.IGNORECASE
)
_LOW_RANK_WORDS = re.compile(r"\b(lowest|least|worst|minimum)\b", flags=re.IGNORECASE)
_PRODUCT_WORD = re.compile(r"\bproducts?\b", flags=re.IGNORECASE)
_SOLD_WORDS = re.compile(r"\b(sold|selling|sales)\b", flags=re.IGNORECASE)
_EXPENSE_WORD = re.compile(r"\bexpenses?\b", flags=re.IGNORECASE)
_CATEGORY_WORD = re.compile(r"\bcategor(?:y|ies)\b", flags=re.IGNORECASE)
_VALUE_WORDS = re.compile(
    r"\b(revenue|sales\s+(?:value|amount)|sales\s+revenue|value|amount|earnings?)\b",
    flags=re.IGNORECASE,
)
_YEARS_PATTERN = re.compile(
    # ``yeare`` is a common one-character typo in free-form questions.  This
    # deliberately accepts only close variants of "year", not arbitrary text.
    r"\b(?:last|past)\s+(?:(\d+)|(one|two|three|four|five))\s+year(?:s|e|es)?\b",
    flags=re.IGNORECASE,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _columns_by_table(database_uri: str) -> dict[str, dict[str, str]]:
    """Return lowercase-to-original column names without reading table data."""

    engine = create_engine(database_uri)
    try:
        inspector = inspect(engine)
        return {
            table: {str(column["name"]).lower(): str(column["name"]) for column in inspector.get_columns(table)}
            for table in inspector.get_table_names()
        }
    finally:
        engine.dispose()


def _period_years(question: str) -> int | None:
    match = _YEARS_PATTERN.search(question)
    if not match:
        return None
    numeric, word = match.groups()
    return int(numeric) if numeric else _NUMBER_WORDS[word.lower()]


def _is_ranked_product_sales_question(question: str) -> bool:
    """Recognise a ranking request, rather than one exact sentence shape."""

    return bool(_RANK_WORDS.search(question) and _PRODUCT_WORD.search(question) and _SOLD_WORDS.search(question))


def _is_expense_category_question(question: str) -> bool:
    """Recognise a category-wise expense breakdown in ordinary phrasing."""

    return bool(_EXPENSE_WORD.search(question) and _CATEGORY_WORD.search(question))


def _is_product_category_sales_summary(question: str) -> bool:
    """Recognise a full category sales breakdown with all requested metrics."""

    question_lower = question.lower()
    return bool(
        _PRODUCT_WORD.search(question)
        and _CATEGORY_WORD.search(question)
        and _SOLD_WORDS.search(question)
        and "quantity" in question_lower
        and _VALUE_WORDS.search(question)
        and re.search(r"\b(?:per\s+unit|average)\b", question_lower)
    )


def _is_product_category_period_comparison(question: str) -> bool:
    """Recognise an adjacent-period category sales comparison."""

    question_lower = question.lower()
    return bool(
        _PRODUCT_WORD.search(question)
        and _CATEGORY_WORD.search(question)
        and _SOLD_WORDS.search(question)
        and re.search(r"\b(?:last|past)\s+two\s+years?\b", question_lower)
        and re.search(r"\b(?:preceding|previous)\s+two\s+years?\b", question_lower)
        and re.search(r"\b(?:percentage|percent)\s+change\b", question_lower)
    )


def _quote_identifier(value: str) -> str:
    """Quote an inspected SQLite identifier; never use a user-supplied name."""

    return '"' + value.replace('"', '""') + '"'


def _build_expense_category_query(question: str, tables: dict[str, dict[str, str]]) -> str | None:
    """Build an exact category-wise expense total from an inspected table.

    Spreadsheet imports often prefix a table name (for example,
    ``_09_expenses_expenses``), so route by its columns and not by a fixed
    filename.  Requiring exactly one compatible table keeps this deterministic
    route conservative when an uploaded workspace contains several ledgers.
    """

    matches = []
    for table, columns in tables.items():
        category = columns.get("expense_category") or columns.get("category")
        date = columns.get("expense_date") or columns.get("date")
        amount = columns.get("amount") or columns.get("expense_amount")
        if category and date and amount and "expense" in table.lower():
            matches.append((table, category, date, amount))
    if len(matches) != 1:
        return None

    table, category, date, amount = matches[0]
    years = _period_years(question)
    where_clause = f"\nWHERE e.{_quote_identifier(date)} >= DATE('now', '-{years} years')" if years else ""
    direction = "ASC" if _LOW_RANK_WORDS.search(question) else "DESC"
    # "highest expense category" means the single category with the largest
    # aggregate.  Without a rank word, "category-wise" remains a complete
    # breakdown so users can compare every category.
    limit_clause = "\nLIMIT 1" if _RANK_WORDS.search(question) else ""
    return (
        f"SELECT e.{_quote_identifier(category)} AS expense_category, "
        f"ROUND(SUM(e.{_quote_identifier(amount)}), 2) AS total_expenses\n"
        f"FROM {_quote_identifier(table)} AS e"
        f"{where_clause}\n"
        f"GROUP BY e.{_quote_identifier(category)}\n"
        f"ORDER BY total_expenses {direction}"
        f"{limit_clause}"
    )


def _build_product_category_sales_query(question: str, tables: dict[str, dict[str, str]]) -> str | None:
    """Build a weighted sales-value-per-unit breakdown from inspected joins."""

    product_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"product_id", "category"}.issubset(columns)
    ]
    item_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"invoice_id", "product_id", "quantity", "line_total"}.issubset(columns)
    ]
    invoice_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"invoice_id", "invoice_date"}.issubset(columns)
    ]
    if len(product_tables) != 1 or len(item_tables) != 1 or len(invoice_tables) != 1:
        return None

    product_table, product_columns = product_tables[0]
    item_table, item_columns = item_tables[0]
    invoice_table, invoice_columns = invoice_tables[0]
    quote = _quote_identifier
    p_id, p_category = quote(product_columns["product_id"]), quote(product_columns["category"])
    i_id, i_product = quote(item_columns["invoice_id"]), quote(item_columns["product_id"])
    i_quantity, i_value = quote(item_columns["quantity"]), quote(item_columns["line_total"])
    s_id, s_date = quote(invoice_columns["invoice_id"]), quote(invoice_columns["invoice_date"])
    years = _period_years(question)
    where_clause = f"\nWHERE s.{s_date} >= DATE('now', '-{years} years')" if years else ""
    direction = "ASC" if re.search(r"\b(?:ascending|asc|lowest|least)\b", question, flags=re.IGNORECASE) else "DESC"
    return (
        f"SELECT p.{p_category} AS product_category, "
        f"SUM(i.{i_quantity}) AS total_quantity_sold, "
        f"ROUND(SUM(i.{i_value}), 2) AS total_sales_value, "
        f"ROUND(SUM(i.{i_value}) / NULLIF(SUM(i.{i_quantity}), 0), 2) AS average_sales_value_per_unit\n"
        f"FROM {quote(item_table)} AS i\n"
        f"JOIN {quote(product_table)} AS p ON p.{p_id} = i.{i_product}\n"
        f"JOIN {quote(invoice_table)} AS s ON s.{s_id} = i.{i_id}"
        f"{where_clause}\n"
        f"GROUP BY p.{p_category}\n"
        f"ORDER BY total_sales_value {direction}"
    )


def _build_product_category_period_comparison(
    tables: dict[str, dict[str, str]]
) -> str | None:
    """Compare two exact adjacent two-year sales periods by product category."""

    product_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"product_id", "category"}.issubset(columns)
    ]
    item_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"invoice_id", "product_id", "line_total"}.issubset(columns)
    ]
    invoice_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"invoice_id", "invoice_date"}.issubset(columns)
    ]
    if len(product_tables) != 1 or len(item_tables) != 1 or len(invoice_tables) != 1:
        return None

    product_table, product_columns = product_tables[0]
    item_table, item_columns = item_tables[0]
    invoice_table, invoice_columns = invoice_tables[0]
    quote = _quote_identifier
    p_id, p_category = quote(product_columns["product_id"]), quote(product_columns["category"])
    i_id, i_product, i_value = quote(item_columns["invoice_id"]), quote(item_columns["product_id"]), quote(item_columns["line_total"])
    s_id, s_date = quote(invoice_columns["invoice_id"]), quote(invoice_columns["invoice_date"])
    current_value = f"SUM(CASE WHEN s.{s_date} >= DATE('now', '-2 years') AND s.{s_date} <= DATE('now') THEN i.{i_value} ELSE 0 END)"
    prior_value = f"SUM(CASE WHEN s.{s_date} >= DATE('now', '-4 years') AND s.{s_date} < DATE('now', '-2 years') THEN i.{i_value} ELSE 0 END)"
    return (
        f"SELECT p.{p_category} AS product_category, "
        f"ROUND({current_value}, 2) AS last_two_year_sales_value, "
        f"ROUND({prior_value}, 2) AS preceding_two_year_sales_value, "
        f"ROUND(100.0 * ({current_value} - {prior_value}) / NULLIF({prior_value}, 0), 2) AS percentage_change\n"
        f"FROM {quote(item_table)} AS i\n"
        f"JOIN {quote(product_table)} AS p ON p.{p_id} = i.{i_product}\n"
        f"JOIN {quote(invoice_table)} AS s ON s.{s_id} = i.{i_id}\n"
        f"WHERE s.{s_date} >= DATE('now', '-4 years') AND s.{s_date} <= DATE('now')\n"
        f"GROUP BY p.{p_category}\n"
        "ORDER BY product_category ASC"
    )


def build_schema_guided_query(database_uri: str, question: str, *, dialect: str | None = "sqlite") -> str | None:
    """Build SQL only for a recognised, relationship-safe business question.

    Product-sales rankings, category sales summaries, and category-wise
    expense totals are mapped from the inspected schema, not from memorised
    spreadsheet names. ``highest sold product`` is greatest *quantity* sold;
    ``lowest``/``least`` reverses the ranking. A ``last N years`` phrase is
    evaluated by SQLite at execution time, keeping the result relative to the
    day of the query.
    """

    if dialect != "sqlite":
        return None

    try:
        tables = _columns_by_table(database_uri)
    except (SQLAlchemyError, ModuleNotFoundError, ImportError):
        return None

    if _is_expense_category_question(question):
        return _build_expense_category_query(question, tables)

    if _is_product_category_period_comparison(question):
        return _build_product_category_period_comparison(tables)

    if _is_product_category_sales_summary(question):
        return _build_product_category_sales_query(question, tables)

    if not _is_ranked_product_sales_question(question):
        return None

    product_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"product_id", "product_name"}.issubset(columns)
    ]
    item_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"invoice_id", "product_id", "quantity"}.issubset(columns)
    ]
    invoice_tables = [
        (table, columns)
        for table, columns in tables.items()
        if {"invoice_id", "invoice_date"}.issubset(columns)
    ]
    if len(product_tables) != 1 or len(item_tables) != 1 or len(invoice_tables) != 1:
        return None

    product_table, product_columns = product_tables[0]
    item_table, item_columns = item_tables[0]
    invoice_table, invoice_columns = invoice_tables[0]
    if _VALUE_WORDS.search(question) and "line_total" not in item_columns:
        return None

    # These names originate from SQLAlchemy inspection, not user input.  Quote
    # them because spreadsheet-derived table names can begin with a digit.
    quote = _quote_identifier
    p_id, p_name = quote(product_columns["product_id"]), quote(product_columns["product_name"])
    i_id, i_product, i_quantity = quote(item_columns["invoice_id"]), quote(item_columns["product_id"]), quote(item_columns["quantity"])
    s_id, s_date = quote(invoice_columns["invoice_id"]), quote(invoice_columns["invoice_date"])
    measure = quote(item_columns["line_total"]) if _VALUE_WORDS.search(question) else i_quantity
    measure_alias = "sales_value" if _VALUE_WORDS.search(question) else "units_sold"
    direction = "ASC" if _LOW_RANK_WORDS.search(question) else "DESC"

    where_clause = ""
    years = _period_years(question)
    if years:
        where_clause = f"\nWHERE s.{s_date} >= DATE('now', '-{years} years')"

    return (
        f"SELECT p.{p_id} AS product_id, p.{p_name} AS product_name, SUM(i.{measure}) AS {measure_alias}\n"
        f"FROM {quote(item_table)} AS i\n"
        f"JOIN {quote(product_table)} AS p ON p.{p_id} = i.{i_product}\n"
        f"JOIN {quote(invoice_table)} AS s ON s.{s_id} = i.{i_id}"
        f"{where_clause}\n"
        f"GROUP BY p.{p_id}, p.{p_name}\n"
        f"ORDER BY {measure_alias} {direction}\n"
        "LIMIT 1"
    )


__all__ = ["build_schema_guided_query"]
