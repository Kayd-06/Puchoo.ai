#!/usr/bin/env python3
"""Run baseline and additional unseen Text-to-SQL acceptance cases."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import mlx.core as mx
from mlx_lm import load

from sql_acceptance_suite import CASES, DEFAULT_DB, build_fixture, run_case
from sql_bench import introspect_schema


EXTRA_CASES = [
    {
        "name": "attendance_boundary",
        "question": "Show Grade 10 students with attendance below 71 percent. Return name and attendance percentage ordered by name.",
        "expected": [("Asha Mehta", 70.0), ("Karan Singh", 70.0), ("Mira Shah", 68.0), ("Nisha Rao", 70.0)],
    },
    {
        "name": "unpaid_fee_boundary",
        "question": "Show Grade 10 students whose unpaid fees are more than 10000. Return name and unpaid fees ordered by unpaid fees descending.",
        "expected": [("Ravi Kumar", 25000), ("Mira Shah", 16000), ("Asha Mehta", 15000), ("Karan Singh", 11000)],
    },
    {
        "name": "average_threshold_variant",
        "question": "Show Grade 10 students whose average marks are below 55. Return name and average marks ordered by name.",
        "expected": [("Asha Mehta", 52.5), ("Mira Shah", 52.5)],
    },
    {
        "name": "combined_threshold_variant",
        "question": "For Grade 10, show students with attendance below 71 percent, average marks below 55, and unpaid fees above 14000. Return name, attendance percentage, average marks, and unpaid fees ordered by name.",
        "expected": [("Asha Mehta", 70.0, 52.5, 15000), ("Mira Shah", 68.0, 52.5, 16000)],
    },
    {
        "name": "no_low_average",
        "question": "Show Grade 10 students whose average marks are below 40. Return name and average marks.",
        "expected": [],
    },
    {
        "name": "single_subject_boundary",
        "question": "Show Grade 10 students with at least one subject mark below 51. Return each name once, ordered by name.",
        "expected": [("Asha Mehta",), ("Mira Shah",), ("Nisha Rao",)],
    },
    {
        "name": "mathematics_active_enrollment",
        "question": "Show students with an active student record and an active enrollment in courses taught by Mathematics department teachers. Return student name and course name ordered by student name.",
        "expected": [("Asha Mehta", "Algebra"), ("Nisha Rao", "Algebra")],
    },
    {
        "name": "invoice_status_filter",
        "question": "Show partial invoices. Return customer name and total amount ordered by customer name.",
        "expected": [("Cedar Stores", 75000.0)],
    },
    {
        "name": "customer_city_join",
        "question": "Show unpaid or partial invoices for customers in Pune. Return customer name, total amount, and payment status ordered by customer name.",
        "expected": [("Alpha Books", 50000.0, "unpaid"), ("Cedar Stores", 75000.0, "partial")],
    },
    {
        "name": "date_filter_without_aggregate",
        "question": "Show Admissions expenses in 2026. Return amount and category ordered by amount descending.",
        "expected": [(5000.0, "marketing")],
    },
    {
        "name": "date_aggregate_other_department",
        "question": "What were total Academics expenses in 2025? Return the total expense amount.",
        "expected": [(30000.0,)],
    },
    {
        "name": "inactive_student_filter",
        "question": "Show inactive students. Return name and class name ordered by name.",
        "expected": [("Aman Das", "Grade 9")],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-attempts", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--report-dir", default="model_training/evaluation/reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    build_fixture(db_path)
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    schema = introspect_schema(connection)
    cases = CASES + EXTRA_CASES

    print("Loading local SQL model once for the extended acceptance suite...")
    model, tokenizer = load(args.model, adapter_path=args.adapter)
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"\n[{index}/{len(cases)}] {case['name']}")
        result = run_case(connection, model, tokenizer, schema, case, args.max_attempts)
        results.append(result)
        print("PASS" if result["passed"] else f"FAIL — {result['reason']}")
        print(f"Latency: {result['latency_seconds']}s; attempts: {len(result['attempts'])}")

    passed = sum(row["passed"] for row in results)
    latencies = sorted(row["latency_seconds"] for row in results)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "adapter": args.adapter,
        "database": str(db_path),
        "passed": passed,
        "total": len(results),
        "pass_rate": round(passed / len(results), 3),
        "mean_latency_seconds": round(sum(latencies) / len(latencies), 3),
        "p95_latency_seconds": latencies[max(0, int(len(latencies) * 0.95) - 1)],
        "peak_memory_gb": round(mx.get_peak_memory() / 1e9, 3),
        "results": results,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"extended_acceptance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("\nEXTENDED ACCEPTANCE SUMMARY")
    print(f"Passed: {passed}/{len(results)}")
    print(f"Pass rate: {report['pass_rate']:.1%}")
    print(f"Mean latency: {report['mean_latency_seconds']}s")
    print(f"P95 latency: {report['p95_latency_seconds']}s")
    print(f"Peak memory: {report['peak_memory_gb']} GB")
    print(f"Evidence report: {report_path}")
    connection.close()
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
