# Puchoo.ai

Puchoo.ai turns natural-language analytics questions into transparent SQL proposals. It implements a deliberate **ask → review → run → verify** workflow over an existing, workspace-scoped SQLite database. It never seeds, fabricates, or mutates source data.

## What is included

```text
apps/
├── core/executor.py                 # Guarded read-only database execution boundary
├── core/verification.py             # Independent Claude describe-and-compare pass
├── core/workspaces.py               # Workspace validation and schema inspection
└── ui/
    ├── Home.py                      # Activity derived from the active workspace
    ├── components/app_shell.py      # Shared theme, sidebar, session state
    └── pages/
        ├── 1_Ask_a_Question.py      # Draft, review, execute, and verify
        ├── 2_Query_History.py       # Workspace-local audit trail
        ├── 3_Guardrail_Settings.py  # Result limits and safety controls
        └── 4_My_Data.py             # SQLite workspace setup and schema view
```

Workspaces and histories are isolated in the current Streamlit session. Production persistence, authentication, and tenancy remain backend concerns.

## Run locally

Use Python 3.10 or newer. The English-only local-model pilot requires Apple
Silicon and the MLX dependencies already installed in the project's model
training environment.

First start the local SQL model in one Terminal window:

```bash
cd /Volumes/ssd/Puchoo.ai
source model_training/.venv_ssd/bin/activate
HF_HOME=/Volumes/ssd/Puchoo.ai/model_training/hf_cache \
caffeinate -dimsu mlx_lm.server \
  --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
  --host 127.0.0.1 --port 8080 --temp 0 --max-tokens 350
```

Then, in a second Terminal window, start Puchoo:

```bash
cd /Volumes/ssd/Puchoo.ai
source model_training/.venv_ssd/bin/activate
streamlit run apps/ui/Home.py
```

To run the lightweight safety-flow tests:

```bash
python -m unittest discover -s tests
```

## Safe execution and verification

- A question is answered automatically only after its SQL passes the read-only guardrails and database query-plan validation. The generated SQL remains available in an optional “How this answer was retrieved” panel.
- The execution boundary parses SQL with SQLGlot, accepts one `SELECT` only, rejects data-changing CTEs and multiple statements, and clamps the outermost `LIMIT`.
- SQLite is also set to `query_only` for execution.
- Before execution, the local model proposal is parsed by the guardrails and compiled with `EXPLAIN` against the connected database. It can receive up to two repair attempts using only validation feedback.
- A separate Claude call describes and compares the question, SQL, and bounded result sample. `VERIFICATION_MISMATCH` is surfaced as an unsafe result; unavailable verification is never represented as a confidence score.
- No credentials or source data are stored in the UI.

## Configuration

Copy `.env.example` to a local, uncommitted `.env` when credentials are ready. The default SQL provider is the local MLX server, so it needs no model API key. `ANTHROPIC_API_KEY` keeps the independent post-execution verifier available. Sarvam settings are retained for a later multilingual release; voice input and translation are intentionally disabled in this English-only pilot.

## Model routing

- SQL proposal generation: local Qwen2.5-Coder-7B-Instruct-4bit through MLX (`127.0.0.1:8080` by default)
- Result verification and lightweight answer checks: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Voice and translation: disabled for this English-only pilot; Sarvam is reserved for the later multilingual release
