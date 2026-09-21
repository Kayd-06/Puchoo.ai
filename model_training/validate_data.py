"""Validate the training format and execute all held-out expected SQL."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DATA = Path(__file__).resolve().parent / "data"


def ddl(schema: str) -> list[str]:
    statements = []
    for part in schema.split(";"):
        table, columns = part.split("(", 1)
        statements.append(f"CREATE TABLE {table.strip()} ({columns}")
    return statements


def validate_chat_file(path: Path) -> int:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    for row in rows:
        messages = row["messages"]
        assert [message["role"] for message in messages] == ["system", "user", "assistant"]
        assert messages[-1]["content"].lstrip().upper().startswith("SELECT ")
        assert "Schema:" in messages[1]["content"]
    return len(rows)


def validate_executable_cases() -> int:
    cases = json.loads((DATA / "test_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        connection = sqlite3.connect(":memory:")
        try:
            for statement in ddl(case["schema"]):
                connection.execute(statement)
            for statement in case["setup"]:
                connection.execute(statement)
            rows = connection.execute(case["sql"]).fetchall()
            assert rows, f"Expected SQL returned no rows: {case['question']}"
        finally:
            connection.close()
    return len(cases)


def main() -> None:
    counts = {split: validate_chat_file(DATA / f"{split}.jsonl") for split in ("train", "valid", "test")}
    executable = validate_executable_cases()
    print(f"Validated {counts['train']} train, {counts['valid']} validation, {counts['test']} held-out chat cases; executed {executable} acceptance cases.")


if __name__ == "__main__":
    main()
