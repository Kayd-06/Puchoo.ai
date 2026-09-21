"""Create a synthetic, PII-free pilot dataset for Finance/Education SQL.

The generated JSONL files contain only chat messages, which is the format
expected by mlx-lm. The separate test_cases.json is used only for executable
acceptance testing and is never supplied to training.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SYSTEM = "Generate exactly one read-only SQLite SELECT query. Use only the supplied schema. Return SQL only."


def record(schema: str, question: str, sql: str) -> dict[str, object]:
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Schema:\n{schema}\nQuestion: {question}"},
        {"role": "assistant", "content": sql},
    ]}


TRAIN_FAMILIES = [
    (
        "financial_transactions(id INTEGER, transaction_date TEXT, category TEXT, amount REAL, transaction_type TEXT)",
        "Show total {kind} by category for {year}.",
        "SELECT category, SUM(amount) AS total_amount FROM financial_transactions WHERE transaction_type = '{kind}' AND transaction_date >= '{year}-01-01' AND transaction_date < '{next_year}-01-01' GROUP BY category",
    ),
    (
        "budgets(department TEXT, fiscal_year INTEGER, allocated_amount REAL, spent_amount REAL)",
        "Which departments {comparison} their allocated budget in {year}?",
        "SELECT department, allocated_amount, spent_amount FROM budgets WHERE fiscal_year = {year} AND spent_amount {operator} allocated_amount",
    ),
    (
        "invoices(id INTEGER, customer_name TEXT, due_date TEXT, amount REAL, status TEXT)",
        "List {status} invoices overdue on {date}, highest amount first.",
        "SELECT id, customer_name, due_date, amount FROM invoices WHERE status = '{status}' AND due_date < '{date}' ORDER BY amount DESC",
    ),
    (
        "students(id INTEGER, programme TEXT, cohort_year INTEGER); enrolments(student_id INTEGER, course_id INTEGER, final_score REAL, attendance_pct REAL); courses(id INTEGER, title TEXT, department TEXT)",
        "Show the average final score for each course in the {department} department.",
        "SELECT c.title, AVG(e.final_score) AS average_final_score FROM enrolments AS e JOIN courses AS c ON e.course_id = c.id WHERE c.department = '{department}' GROUP BY c.id, c.title",
    ),
    (
        "students(id INTEGER, programme TEXT); enrolments(student_id INTEGER, course_id INTEGER, attendance_pct REAL)",
        "Count students in each programme with attendance below {threshold} percent.",
        "SELECT s.programme, COUNT(DISTINCT s.id) AS student_count FROM students AS s JOIN enrolments AS e ON e.student_id = s.id WHERE e.attendance_pct < {threshold} GROUP BY s.programme",
    ),
    (
        "assessments(id INTEGER, course_id INTEGER, assessment_type TEXT, maximum_score REAL); assessment_results(student_id INTEGER, assessment_id INTEGER, score REAL)",
        "For every assessment, show its average percentage score.",
        "SELECT a.id, a.assessment_type, AVG(r.score * 100.0 / a.maximum_score) AS average_percentage FROM assessments AS a JOIN assessment_results AS r ON r.assessment_id = a.id GROUP BY a.id, a.assessment_type, a.maximum_score",
    ),
]


TEST_CASES = [
    {
        "schema": "ledger_entries(id INTEGER, entry_date TEXT, account TEXT, debit REAL, credit REAL)",
        "question": "Calculate total debit and total credit for every account in 2025.",
        "sql": "SELECT account, SUM(debit) AS total_debit, SUM(credit) AS total_credit FROM ledger_entries WHERE entry_date >= '2025-01-01' AND entry_date < '2026-01-01' GROUP BY account ORDER BY account",
        "setup": [
            "INSERT INTO ledger_entries VALUES (1, '2025-01-05', 'Cash', 100, 0)",
            "INSERT INTO ledger_entries VALUES (2, '2025-02-01', 'Cash', 0, 40)",
            "INSERT INTO ledger_entries VALUES (3, '2025-03-01', 'Sales', 0, 300)",
            "INSERT INTO ledger_entries VALUES (4, '2024-12-31', 'Cash', 25, 0)",
        ],
    },
    {
        "schema": "courses(id INTEGER, title TEXT); assignments(id INTEGER, course_id INTEGER, due_date TEXT); submissions(id INTEGER, assignment_id INTEGER, student_id INTEGER, submitted_at TEXT)",
        "question": "List assignments that had no submissions by their due date.",
        "sql": "SELECT a.id, a.course_id, a.due_date FROM assignments AS a LEFT JOIN submissions AS s ON s.assignment_id = a.id AND s.submitted_at <= a.due_date WHERE s.id IS NULL ORDER BY a.id",
        "setup": [
            "INSERT INTO courses VALUES (1, 'Math')",
            "INSERT INTO assignments VALUES (1, 1, '2025-03-10')",
            "INSERT INTO assignments VALUES (2, 1, '2025-03-12')",
            "INSERT INTO submissions VALUES (1, 1, 10, '2025-03-09')",
            "INSERT INTO submissions VALUES (2, 2, 11, '2025-03-15')",
        ],
    },
    {
        "schema": "course_sessions(course_id INTEGER, session_date TEXT, scheduled_count INTEGER, attended_count INTEGER)",
        "question": "Which courses had an attendance rate below 80 percent in March 2025?",
        "sql": "SELECT course_id, SUM(attended_count) * 100.0 / SUM(scheduled_count) AS attendance_rate FROM course_sessions WHERE session_date >= '2025-03-01' AND session_date < '2025-04-01' GROUP BY course_id HAVING SUM(attended_count) * 100.0 / SUM(scheduled_count) < 80 ORDER BY course_id",
        "setup": [
            "INSERT INTO course_sessions VALUES (1, '2025-03-01', 20, 15)",
            "INSERT INTO course_sessions VALUES (1, '2025-03-08', 20, 16)",
            "INSERT INTO course_sessions VALUES (2, '2025-03-01', 20, 18)",
            "INSERT INTO course_sessions VALUES (3, '2025-04-01', 20, 0)",
        ],
    },
]


def ddl(schema: str) -> list[str]:
    return [f"CREATE TABLE {table.strip()} ({columns})" for table, columns in (part.split("(", 1) for part in schema.split(";"))]


def build_examples() -> list[dict[str, object]]:
    random.seed(42)
    examples: list[dict[str, object]] = []
    for _ in range(300):
        schema, question_template, sql_template = random.choice(TRAIN_FAMILIES)
        year = random.choice((2023, 2024, 2025))
        values = {
            "kind": random.choice(("expense", "income")),
            "year": year,
            "next_year": year + 1,
            "comparison": random.choice(("exceeded", "did not exceed")),
            "operator": random.choice((">", "<=")),
            "status": random.choice(("unpaid", "pending")),
            "date": random.choice(("2025-06-01", "2026-01-15")),
            "department": random.choice(("Mathematics", "Science", "Commerce")),
            "threshold": random.choice((60, 70, 75, 80)),
        }
        if "{comparison}" in question_template:
            values["operator"] = ">" if values["comparison"] == "exceeded" else "<="
        examples.append(record(schema, question_template.format(**values), sql_template.format(**values)))
    return examples


def write_jsonl(path: Path, examples: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(example) + "\n" for example in examples), encoding="utf-8")


def main() -> None:
    DATA.mkdir(exist_ok=True)
    examples = build_examples()
    write_jsonl(DATA / "train.jsonl", examples[:240])
    write_jsonl(DATA / "valid.jsonl", examples[240:270])
    write_jsonl(DATA / "test.jsonl", [record(case["schema"], case["question"], case["sql"]) for case in TEST_CASES])
    (DATA / "test_cases.json").write_text(json.dumps(TEST_CASES, indent=2) + "\n", encoding="utf-8")
    print("Wrote 240 train, 30 validation, and 3 held-out executable test cases.")


if __name__ == "__main__":
    main()
