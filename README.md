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

Use Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run apps/ui/Home.py
```

To run the lightweight safety-flow tests:

```bash
python -m unittest discover -s tests
```

## Safe execution and verification

- Generated SQL is shown for review and never runs automatically.
- The execution boundary parses SQL with SQLGlot, accepts one `SELECT` only, rejects data-changing CTEs and multiple statements, and clamps the outermost `LIMIT`.
- SQLite is also set to `query_only` for execution.
- A separate Claude call describes and compares the question, SQL, and bounded result sample. `VERIFICATION_MISMATCH` is surfaced as an unsafe result; unavailable verification is never represented as a confidence score.
- No credentials or source data are stored in the UI.

## Configuration

Copy `.env.example` to a local, uncommitted `.env` when credentials are ready. `ANTHROPIC_API_KEY` powers Claude Sonnet 5 SQL generation and Claude Haiku 4.5 verification; `SARVAM_API_KEY` enables optional Indian-language voice input plus answer translation/transliteration. Without either key, the relevant UI control explains what is unavailable and never fabricates output.

## Model routing

- SQL proposal generation: Claude Sonnet 5 (`claude-sonnet-5`)
- Result verification and lightweight answer checks: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Indian-language voice input: Sarvam Saaras (`saaras:v3`)
- Regional-language output: Sarvam Translate (`sarvam-translate:v1`) and transliteration
