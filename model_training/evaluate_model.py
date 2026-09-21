"""Execute generated SQL against held-out fixtures and compare result rows.

Run this only after a LoRA adapter exists. A model passes a case when it emits
one SELECT that executes and returns exactly the expected columns and rows.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from mlx_lm import generate, load


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SYSTEM = "Generate exactly one read-only SQLite SELECT query. Use only the supplied schema. Return SQL only."


def ddl(schema: str) -> list[str]:
    statements = []
    for part in schema.split(";"):
        table, columns = part.split("(", 1)
        statements.append(f"CREATE TABLE {table.strip()} ({columns}")
    return statements


def prompt(tokenizer: object, schema: str, question: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Schema:\n{schema}\nQuestion: {question}"},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def clean_sql(text: str) -> str:
    sql = text.strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    return sql.split(";")[0].strip()


def query(connection: sqlite3.Connection, sql: str) -> tuple[list[str], list[tuple[object, ...]]]:
    cursor = connection.execute(sql)
    return [column[0] for column in cursor.description], cursor.fetchall()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--adapter-path", required=True)
    parser.add_argument("--max-tokens", type=int, default=256)
    args = parser.parse_args()

    model, tokenizer = load(args.model, adapter_path=args.adapter_path)
    cases = json.loads((DATA / "test_cases.json").read_text(encoding="utf-8"))
    passed = 0
    for number, case in enumerate(cases, start=1):
        output = generate(model, tokenizer, prompt=prompt(tokenizer, case["schema"], case["question"]), max_tokens=args.max_tokens, temp=0.0)
        sql = clean_sql(output)
        connection = sqlite3.connect(":memory:")
        try:
            for statement in ddl(case["schema"]):
                connection.execute(statement)
            for statement in case["setup"]:
                connection.execute(statement)
            expected = query(connection, case["sql"])
            actual = query(connection, sql) if sql.upper().startswith("SELECT ") else None
            success = actual == expected
        except sqlite3.Error as exc:
            success = False
            actual = f"SQLite error: {exc}"
        finally:
            connection.close()
        passed += int(success)
        print(f"Case {number}: {'PASS' if success else 'FAIL'}")
        if not success:
            print(f"  Question: {case['question']}")
            print(f"  Generated: {sql or '[empty]'}")
            print(f"  Expected: {case['sql']}")
            print(f"  Actual: {actual}")
    print(f"Execution accuracy: {passed}/{len(cases)} ({passed / len(cases):.0%})")
    raise SystemExit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()
