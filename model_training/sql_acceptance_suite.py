#!/usr/bin/env python3
"""Standalone acceptance suite for the local guarded Text-to-SQL prototype."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import mlx.core as mx
from mlx_lm import load

from sql_bench import (
    BLOCKED_WORDS,
    Attempt,
    generate_sql,
    introspect_schema,
    safety_and_syntax_checks,
    semantic_checks,
)


ROOT = Path("model_training")
DEFAULT_DB = ROOT / "evaluation" / "puchoo_acceptance_suite.db"


def build_fixture(path: Path) -> None:
    """Create only the named disposable acceptance database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE students (
            student_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE attendance (
            attendance_id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            attendance_percentage REAL NOT NULL
        );
        CREATE TABLE grades (
            grade_id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            marks REAL NOT NULL,
            exam_term TEXT NOT NULL
        );
        CREATE TABLE fees (
            fee_id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            amount_due INTEGER NOT NULL,
            amount_paid INTEGER NOT NULL,
            due_date TEXT NOT NULL
        );
        CREATE TABLE teachers (
            teacher_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            department TEXT NOT NULL
        );
        CREATE TABLE courses (
            course_id INTEGER PRIMARY KEY,
            course_name TEXT NOT NULL,
            teacher_id INTEGER NOT NULL
        );
        CREATE TABLE enrollments (
            enrollment_id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            enrollment_status TEXT NOT NULL
        );
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            customer_name TEXT NOT NULL,
            city TEXT NOT NULL
        );
        CREATE TABLE invoices (
            invoice_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            invoice_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            payment_status TEXT NOT NULL
        );
        CREATE TABLE expenses (
            expense_id INTEGER PRIMARY KEY,
            department TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL
        );
        """
    )
    db.executemany(
        "INSERT INTO students VALUES (?, ?, ?, ?)",
        [
            (1, "Asha Mehta", "Grade 10", "active"),
            (2, "Ravi Kumar", "Grade 10", "active"),
            (3, "Mira Shah", "Grade 10", "active"),
            (4, "Aman Das", "Grade 9", "inactive"),
            (5, "Nisha Rao", "Grade 10", "active"),
            (6, "Karan Singh", "Grade 10", "active"),
        ],
    )
    db.executemany(
        "INSERT INTO attendance VALUES (?, ?, ?)",
        [(1, 1, 70.0), (2, 2, 82.0), (3, 3, 68.0), (4, 4, 60.0), (5, 5, 70.0), (6, 6, 70.0)],
    )
    db.executemany(
        "INSERT INTO grades VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, "Mathematics", 50.0, "Final"), (2, 1, "Science", 55.0, "Final"),
            (3, 2, "Mathematics", 85.0, "Final"), (4, 2, "Science", 90.0, "Final"),
            (5, 3, "Mathematics", 50.0, "Final"), (6, 3, "Science", 55.0, "Final"),
            (7, 4, "Mathematics", 40.0, "Final"), (8, 4, "Science", 45.0, "Final"),
            (9, 5, "Mathematics", 50.0, "Final"), (10, 5, "Science", 80.0, "Final"),
            (11, 6, "Mathematics", 55.0, "Final"), (12, 6, "Science", 70.0, "Final"),
        ],
    )
    db.executemany(
        "INSERT INTO fees VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, 30000, 15000, "2026-03-31"), (2, 2, 30000, 5000, "2026-03-31"),
            (3, 3, 20000, 4000, "2026-03-31"), (4, 4, 10000, 0, "2026-03-31"),
            (5, 5, 30000, 25000, "2026-03-31"), (6, 6, 12000, 1000, "2026-03-31"),
        ],
    )
    db.executemany(
        "INSERT INTO teachers VALUES (?, ?, ?)",
        [(1, "Dr. Sen", "Mathematics"), (2, "Ms. Iyer", "Science")],
    )
    db.executemany(
        "INSERT INTO courses VALUES (?, ?, ?)",
        [(1, "Algebra", 1), (2, "Physics", 2)],
    )
    db.executemany(
        "INSERT INTO enrollments VALUES (?, ?, ?, ?)",
        [(1, 1, 1, "active"), (2, 2, 2, "inactive"), (3, 3, 2, "active"), (4, 5, 1, "active")],
    )
    db.executemany(
        "INSERT INTO customers VALUES (?, ?, ?)",
        [(1, "Alpha Books", "Pune"), (2, "Beta Labs", "Mumbai"), (3, "Cedar Stores", "Pune")],
    )
    db.executemany(
        "INSERT INTO invoices VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, "2026-01-10", 50000, "unpaid"),
            (2, 2, "2026-02-15", 20000, "paid"),
            (3, 3, "2026-03-01", 75000, "partial"),
        ],
    )
    db.executemany(
        "INSERT INTO expenses VALUES (?, ?, ?, ?, ?)",
        [
            (1, "Admissions", "2025-02-10", 12000, "marketing"),
            (2, "Admissions", "2025-06-12", 8000, "events"),
            (3, "Academics", "2025-01-08", 30000, "equipment"),
            (4, "Admissions", "2026-01-05", 5000, "marketing"),
        ],
    )
    db.commit()
    db.close()


CASES = [
    {
        "name": "attendance_filter",
        "question": "Show Grade 10 students with attendance below 70 percent. Return name and attendance percentage ordered by name.",
        "expected": [("Mira Shah", 68.0)],
    },
    {
        "name": "unpaid_fee_math",
        "question": "Show Grade 10 students whose unpaid fees are more than 15000. Return name and unpaid fees ordered by unpaid fees descending.",
        "expected": [("Ravi Kumar", 25000), ("Mira Shah", 16000)],
    },
    {
        "name": "average_marks_having",
        "question": "Show Grade 10 students whose average marks are below 60. Return name and average marks ordered by name.",
        "expected": [("Asha Mehta", 52.5), ("Mira Shah", 52.5)],
    },
    {
        "name": "combined_adversarial",
        "question": "For Grade 10, show each student whose attendance is below 75 percent, whose average marks are below 60, and whose unpaid fees are more than 10000. Return student name, attendance percentage, average marks, and unpaid fees. Order by unpaid fees from highest to lowest.",
        "expected": [("Mira Shah", 68.0, 52.5, 16000), ("Asha Mehta", 70.0, 52.5, 15000)],
    },
    {
        "name": "individual_mark_not_average",
        "question": "Show Grade 10 students with at least one subject mark below 55. Return each student name once, ordered by name.",
        "expected": [("Asha Mehta",), ("Mira Shah",), ("Nisha Rao",)],
    },
    {
        "name": "course_teacher_join",
        "question": "Show students with an active student record and an active enrollment in courses taught by Science department teachers. Return student name and course name ordered by student name.",
        "expected": [("Mira Shah", "Physics")],
    },
    {
        "name": "finance_invoice_join",
        "question": "Show unpaid or partial invoices above 40000. Return customer name, total amount, and payment status ordered by total amount descending.",
        "expected": [("Cedar Stores", 75000.0, "partial"), ("Alpha Books", 50000.0, "unpaid")],
    },
    {
        "name": "date_aggregate",
        "question": "What were total Admissions expenses in 2025? Return the total expense amount.",
        "expected": [(20000.0,)],
    },
    {
        "name": "empty_result",
        "question": "Show students with attendance below 10 percent. Return name and attendance percentage.",
        "expected": [],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-attempts", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--report-dir", default=str(ROOT / "evaluation" / "reports"))
    return parser.parse_args()


def run_case(connection, model, tokenizer, schema: str, case: dict, max_attempts: int) -> dict:
    attempts: list[Attempt] = []
    feedback = None
    previous_sql = None
    started = time.perf_counter()

    for number in range(1, max_attempts + 1):
        sql = generate_sql(model, tokenizer, schema, case["question"], feedback, previous_sql)
        errors = safety_and_syntax_checks(connection, sql)
        if sql.upper().startswith("SELECT") and not BLOCKED_WORDS.search(sql):
            errors.extend(semantic_checks(case["question"], sql))

        accepted = not errors
        attempts.append(Attempt(number, sql, accepted, errors))
        if accepted:
            rows = connection.execute(sql).fetchall()
            passed = rows == case["expected"]
            return {
                "name": case["name"],
                "question": case["question"],
                "passed": passed,
                "reason": "" if passed else "Returned rows differ from the expected answer.",
                "rows": rows,
                "expected": case["expected"],
                "latency_seconds": round(time.perf_counter() - started, 3),
                "attempts": [asdict(item) for item in attempts],
            }
        feedback = errors
        previous_sql = sql

    return {
        "name": case["name"],
        "question": case["question"],
        "passed": False,
        "reason": "No safe, executable, semantically acceptable SQL was produced.",
        "rows": [],
        "expected": case["expected"],
        "latency_seconds": round(time.perf_counter() - started, 3),
        "attempts": [asdict(item) for item in attempts],
    }


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    build_fixture(db_path)
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    schema = introspect_schema(connection)

    print("Loading local SQL model once for the full acceptance suite...")
    model, tokenizer = load(args.model, adapter_path=args.adapter)

    results = []
    for index, case in enumerate(CASES, start=1):
        print(f"\n[{index}/{len(CASES)}] {case['name']}")
        result = run_case(connection, model, tokenizer, schema, case, args.max_attempts)
        results.append(result)
        print("PASS" if result["passed"] else f"FAIL — {result['reason']}")
        print(f"Latency: {result['latency_seconds']}s; attempts: {len(result['attempts'])}")

    passed = sum(result["passed"] for result in results)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "adapter": args.adapter,
        "database": str(db_path),
        "peak_memory_gb": round(mx.get_peak_memory() / 1e9, 3),
        "passed": passed,
        "total": len(results),
        "pass_rate": round(passed / len(results), 3),
        "results": results,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"acceptance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("\nACCEPTANCE SUMMARY")
    print(f"Passed: {passed}/{len(results)}")
    print(f"Pass rate: {report['pass_rate']:.1%}")
    print(f"Peak memory: {report['peak_memory_gb']} GB")
    print(f"Evidence report: {report_path}")
    connection.close()
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
