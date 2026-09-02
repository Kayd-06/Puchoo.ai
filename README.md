# Puchoo.ai

Puchoo.ai turns natural-language analytics questions into transparent SQL proposals. This first slice is a Streamlit UI MVP: it demonstrates the deliberate **ask → review → run** flow using safe, local demo data. It does not connect to or execute against a database yet.

## What is included

```text
apps/ui/
├── Home.py                         # Interactive first page; no fabricated results
├── pages/
│   ├── 1_Ask_a_Question.py          # Draft, review, explicitly run a query
│   ├── 2_Query_History.py           # Session-local audit history and feedback
│   └── 3_Guardrail_Settings.py      # Result limits and visible safety controls
├── components/app_shell.py          # Shared theme, sidebar, session state
└── data/demo_data.py                # Safe demo responses; no DB access
```

The page layout follows the UI portion of the proposed application architecture. The backend-facing concerns—connection management, SQL validation, execution, history persistence, authentication, and tenancy—remain intentionally outside this MVP.

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

## Safety behavior in this MVP

- Generated SQL is shown for review and never runs automatically.
- The demo includes a simple natural-language preflight for write-oriented requests. It is illustrative UI behavior—not SQL validation or a security boundary.
- Demo history is stored only in the current Streamlit session.
- No credentials, database connection, schema payload, or source data are included.

When the FastAPI layer is ready, replace `apps/ui/data/demo_data.py` calls with a client that maps to `POST /query`, `GET /history`, and `POST /queries/:id/feedback`. Keep the explicit approval boundary in the UI; SQL parsing, guardrails, row limits, and execution authorization must be enforced server-side.
