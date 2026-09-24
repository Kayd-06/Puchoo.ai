# data_v7_complex_plans

This directory defines the small checked-in template for plan-aware Qwen2.5-Coder-7B QLoRA data. Build the real 2,000-5,000 example dataset privately from reviewed, anonymized failures. Do not commit model weights, adapters, raw customer data, caches, or generated training outputs.

Each JSONL record has:

- `id` and `task`: stable identity and one of `plan_sql`, `clarification`, or `repair`.
- `question`: the original difficult user wording.
- `schema`: relevant SQLite schema only; never raw rows.
- `plan`: the strict planner object used by the app.
- `sql`: correct read-only SQLite SQL, or `null` for clarification.
- `failed_sql` and `database_error`: populated only for reviewed repair examples.
- `repaired_sql`: the expected replacement SELECT for repair examples.

Split real examples before training so the evaluation set contains at least 100 unseen hard questions. Score execution success, result correctness, constraint coverage, clarification accuracy, and SQL safety rather than exact SQL text alone.
