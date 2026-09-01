"""Safe demo responses for the UI-only MVP.

This module deliberately never opens a database connection or executes SQL. It
lets the Streamlit experience demonstrate the review-before-run workflow until
the FastAPI service is available.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from uuid import uuid4


DEFAULT_GUARDRAILS: dict[str, Any] = {
    "max_rows": 500,
    "timeout_seconds": 30,
    "allowed_schema": "main",
    "block_writes": True,
    "block_multiple_statements": True,
    "enforce_complexity_checks": True,
}

SAMPLE_SCHEMA = {
    "orders": ["id", "customer_id", "ordered_at", "region", "total_amount", "status"],
    "customers": ["id", "name", "segment", "created_at", "country"],
    "products": ["id", "name", "category", "unit_price", "is_active"],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _query_id() -> str:
    """Create a distinct audit ID for every generated proposal."""
    return f"qry_{uuid4().hex[:12]}"


def _with_row_limit(sql: str, max_rows: int) -> str:
    """Make the UI's demonstrated result policy visible in the SQL preview."""
    return f"{sql.rstrip().rstrip(';')}\nLIMIT {max_rows};"


def _sales_response(question: str, max_rows: int) -> dict[str, Any]:
    rows = [
        {"month": "Jan", "revenue": 128_400, "orders": 486},
        {"month": "Feb", "revenue": 142_800, "orders": 525},
        {"month": "Mar", "revenue": 155_200, "orders": 562},
        {"month": "Apr", "revenue": 149_600, "orders": 538},
        {"month": "May", "revenue": 168_900, "orders": 601},
        {"month": "Jun", "revenue": 181_300, "orders": 648},
    ]
    return {
        "question": question,
        "sql": """SELECT
  strftime('%Y-%m', ordered_at) AS month,
  ROUND(SUM(total_amount), 2) AS revenue,
  COUNT(*) AS orders
FROM orders
WHERE ordered_at >= date('now', '-6 months')
  AND status = 'completed'
GROUP BY 1
ORDER BY 1;""",
        "explanation": "Groups completed orders by month for the last six months and totals their revenue.",
        "confidence": 94,
        "result_summary": "Revenue rose 41% from January to June, with the strongest month in June.",
        "rows": rows[:max_rows],
        "chart_columns": ("month", "revenue"),
        "estimated_rows": len(rows),
        "execution_ms": 182,
    }


def _customer_response(question: str, max_rows: int) -> dict[str, Any]:
    rows = [
        {"segment": "Enterprise", "customers": 38, "lifetime_value": 428_900},
        {"segment": "Mid-market", "customers": 86, "lifetime_value": 312_400},
        {"segment": "SMB", "customers": 241, "lifetime_value": 195_700},
    ]
    return {
        "question": question,
        "sql": """SELECT
  c.segment,
  COUNT(DISTINCT c.id) AS customers,
  ROUND(SUM(o.total_amount), 2) AS lifetime_value
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
  AND o.status = 'completed'
GROUP BY c.segment
ORDER BY lifetime_value DESC;""",
        "explanation": "Joins customers to completed orders and compares customer counts and revenue by segment.",
        "confidence": 91,
        "result_summary": "Enterprise customers have the highest lifetime value despite being the smallest segment.",
        "rows": rows[:max_rows],
        "chart_columns": ("segment", "lifetime_value"),
        "estimated_rows": len(rows),
        "execution_ms": 214,
    }


def _generic_response(question: str, max_rows: int) -> dict[str, Any]:
    rows = [
        {"region": "North", "revenue": 248_500, "orders": 912},
        {"region": "West", "revenue": 216_300, "orders": 801},
        {"region": "South", "revenue": 194_200, "orders": 723},
        {"region": "East", "revenue": 171_600, "orders": 654},
    ]
    return {
        "question": question,
        "sql": """SELECT
  region,
  ROUND(SUM(total_amount), 2) AS revenue,
  COUNT(*) AS orders
FROM orders
WHERE status = 'completed'
GROUP BY region
ORDER BY revenue DESC;""",
        "explanation": "Summarizes completed-order revenue and order volume by region.",
        "confidence": 88,
        "result_summary": "North is the leading region by both completed-order revenue and volume.",
        "rows": rows[:max_rows],
        "chart_columns": ("region", "revenue"),
        "estimated_rows": len(rows),
        "execution_ms": 163,
    }


def _blocked_response(question: str) -> dict[str, Any]:
    """Represent a deterministic pre-execution write-operation block."""
    return {
        "question": question,
        "sql": "-- No SQL was generated because the request would modify data.",
        "explanation": "The request includes an operation that could change database state.",
        "confidence": 0,
        "result_summary": "No query was executed.",
        "rows": [],
        "chart_columns": ("", ""),
        "estimated_rows": 0,
        "execution_ms": None,
        "id": _query_id(),
        "status": "blocked",
        "guardrail_message": "Blocked: requests to modify, remove, or create data are never allowed.",
        "generated_at": _utc_now().isoformat(),
        "executed": False,
        "feedback": None,
    }


def generate_demo_query(question: str, max_rows: int = 500) -> dict[str, Any]:
    """Return a generated-but-not-executed query for a natural-language question."""
    normalized = question.lower()
    destructive_request = re.search(
        r"\b(delete|drop|update|insert|alter|truncate|create|replace|remove|merge|grant|revoke|call|exec(?:ute)?)\b",
        normalized,
    )
    if destructive_request:
        return _blocked_response(question)
    if any(term in normalized for term in ("customer", "segment", "lifetime")):
        result = _customer_response(question, max_rows)
    elif any(term in normalized for term in ("sales", "revenue", "monthly", "month")):
        result = _sales_response(question, max_rows)
    else:
        result = _generic_response(question, max_rows)

    result["sql"] = _with_row_limit(result["sql"], max_rows)
    result.update(
        {
            "id": _query_id(),
            "status": "approved",
            "guardrail_message": f"Demo policy check passed: SELECT preview includes a {max_rows:,}-row limit.",
            "generated_at": _utc_now().isoformat(),
            "executed": False,
            "feedback": None,
        }
    )
    return result


def execute_demo_query(query: dict[str, Any]) -> dict[str, Any]:
    """Mark a previously approved demo query as executed.

    The returned object mirrors the future execution payload without performing
    SQL. Keeping this boundary explicit prevents the UI from normalizing an
    unsafe auto-run pattern.
    """
    if query.get("status") != "approved":
        raise ValueError("Only an approved query can be executed.")

    executed = deepcopy(query)
    executed["status"] = "executed"
    executed["executed"] = True
    executed["executed_at"] = _utc_now().isoformat()
    return executed


def results_frame(query: dict[str, Any]) -> "pd.DataFrame":
    """Create a dataframe only for rendering/download in the Streamlit UI."""
    import pandas as pd

    return pd.DataFrame(query["rows"])


def seeded_history() -> list[dict[str, Any]]:
    """Return a small, fresh list for a useful first-run history screen."""
    now = _utc_now()
    sales = execute_demo_query(generate_demo_query("How has monthly revenue changed?"))
    sales.update(
        {
            "id": "qry_demo_sales",
            "executed_at": (now - timedelta(hours=2)).isoformat(),
            "feedback": "up",
        }
    )
    customers = execute_demo_query(generate_demo_query("Which customer segments have the highest value?"))
    customers.update(
        {
            "id": "qry_demo_customers",
            "executed_at": (now - timedelta(days=1, hours=3)).isoformat(),
            "feedback": None,
        }
    )
    blocked = {
        "id": "qry_demo_blocked",
        "question": "Delete cancelled orders from last year",
        "sql": "-- No SQL was generated because the request would modify data.",
        "explanation": "The request would modify data.",
        "confidence": 0,
        "status": "blocked",
        "guardrail_message": "Blocked: write operations are never allowed.",
        "generated_at": (now - timedelta(days=2)).isoformat(),
        "executed": False,
        "executed_at": None,
        "estimated_rows": 0,
        "execution_ms": None,
        "rows": [],
        "chart_columns": ("", ""),
        "result_summary": "No query was executed.",
        "feedback": None,
    }
    return [sales, customers, blocked]
