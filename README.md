# Puchoo.ai

Puchoo.ai is a production-grade secure multilingual Text-to-SQL analytics platform. It turns natural-language analytics questions into transparent SQL proposals using a deliberate **ask → review → run → verify** workflow over your existing databases.

It implements a **FastAPI backend as the sole security boundary** and a **React SPA (Vite)** for a premium, secure presentation layer.

## Architecture

- **Backend (`apps/core/` & `apps/api/`)**: FastAPI exposes the core Python execution, verification, and guardrail logic. It handles all authentication, session state, and security. No credentials are leaked to the client.
- **Frontend (`frontend/`)**: Vite + React SPA handling presentation only. Rich Vanilla CSS design system.

### Complex-query intelligence

- Simple supported questions keep the fast deterministic schema-guided path.
- Complex questions are routed through two sequential calls to the same local Qwen2.5-Coder-7B chat model: JSON planning, then SQLite SQL generation.
- The planner can request clarification instead of guessing a metric, timeframe, comparison baseline, or business policy.
- Only 3-6 relevant schema tables are normally sent to the model; no raw database rows are included.
- Failed safe SELECT statements can be repaired by Qwen using the original question, plan, selected schema, previous SQL, and database error. Unsafe SQL is never retried.
- SQLCoder and the `LOCAL_SQL_REPAIR_MODEL_*` settings are no longer used.

## Website and accounts

The public site is a React landing page. Accounts live in `backend/` and are the only place passwords and session tokens are handled. React never stores a token in `localStorage`. FastAPI remains the security boundary.

### Setup

Use Python 3.11 or newer and Node.js 20 or newer.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\migrate.ps1
cd frontend
npm install
```

### Environment

Copy `.env.example` to `.env` at the repo root, or copy `backend/.env.example` to `backend/.env`. Do not commit either file.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL. Defaults to a local SQLite file at `backend/puchoo_auth.db`. Use a Postgres URL when you have one. |
| `FRONTEND_ORIGINS` | Comma-separated origins allowed to call the API with credentials. Default `http://localhost:5173,http://127.0.0.1:5173`. |
| `COOKIE_SECURE` | `true` in production so the session and CSRF cookies are HTTPS-only. |
| `ENVIRONMENT` | `development` or `production`. |
| `SESSION_SECRET` | Secret for the analytics session middleware. Replace it outside local development. |

### Run both apps

From the repo root, in two terminals:

```powershell
.\scripts\dev-backend.ps1
.\scripts\dev-frontend.ps1
```

Or:

```powershell
npm run dev:backend
npm run dev:frontend
```

Open [http://localhost:5173](http://localhost:5173). The Vite dev server proxies `/api` to the backend on port 8000.

`uvicorn backend.main:app` serves accounts and the existing analytics API. `uvicorn apps.api.main:app` does the same if you already use that entrypoint.

Auth tests:

```powershell
.\venv\Scripts\python.exe -m pytest backend/tests -q
```

### How auth works

- `POST /api/v1/auth/signup` accepts `full_name`, `email`, `password`, `confirm_password`, and `workspace_type` (`personal` or `institute`). Institute workspaces also require `institute_name`. Email is stored in lowercase. Passwords need at least 10 characters, including a letter and a number, and are hashed with argon2. A duplicate email gets a generic error.
- `POST /api/v1/auth/login` checks the email and password. The error is always `Invalid email or password`. A correct password does not open a session yet. It emails a 6-digit code that expires in 10 minutes. `POST /api/v1/auth/login/verify` checks that code and then creates the session. SMTP uses `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, and `SMTP_PASSWORD`.
- A successful signup or login creates a server-side session. The raw token is a random 256-bit value. Only its SHA-256 hash is stored. The browser receives it in an HttpOnly `puchoo_session` cookie with `SameSite=Lax` (and `Secure` when `COOKIE_SECURE=true`). Sessions last 7 days and slide forward on authenticated requests.
- `POST /api/v1/auth/logout` revokes that session and clears the cookie. `GET /api/v1/auth/me` returns the current user, or 401.
- State-changing auth requests need a double-submit CSRF token: the non-HttpOnly `csrf_token` cookie and the same value in the `X-CSRF-Token` header.
- Login and signup are limited to 5 attempts per 15 minutes for each IP and each email. The limit returns 429.
- Passwords and tokens are not written to logs.

The landing page is `/`. `/login` and `/signup` are the account forms. `/app` is the signed-in workspace. Logged-in visitors are sent from the account forms to `/app`.

To replace the final call-to-action image, add a file at `frontend/public/cta-visual.png`.

## Run locally

Use Python 3.10 or newer.

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the FastAPI backend:**
   ```bash
   uvicorn apps.api.main:app --reload --port 8000
   ```

3. **Start the React frontend:**
   In a new terminal window:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. Open [http://localhost:5173](http://localhost:5173) in your browser.

## Safe execution and verification

- A question is answered automatically only after its SQL passes the read-only guardrails and database query-plan validation.
- The execution boundary parses SQL with SQLGlot, accepts one `SELECT` only, rejects data-changing CTEs and multiple statements, and clamps the outermost `LIMIT`.
- No credentials or source data are stored in the React UI. The FastAPI layer maintains strict session and tenant boundaries.

## Configuration

Copy `.env.example` to a local, uncommitted `.env` when credentials are ready. The default SQL provider is the local MLX server, so it needs no model API key for basic SQL generation. `ANTHROPIC_API_KEY` enables the independent post-execution verifier.

For a Windows-hosted OpenAI-compatible Qwen server, set:

```env
LOCAL_SQL_MODEL_URL=http://127.0.0.1:8080/v1/chat/completions
LOCAL_SQL_MODEL_NAME=your-finetuned-qwen-sql-7b
LOCAL_SQL_REQUEST_STYLE=chat
LOCAL_SQL_MAX_TOKENS=450
LOCAL_SQL_MAX_ATTEMPTS=2
LOCAL_SQL_SCHEMA_MAX_TABLES=6
LOCAL_SQL_SCHEMA_MAX_CHARS=12000
```

Use the Windows machine's LAN IP instead of `127.0.0.1` only when the app runs on another machine, and restrict port 8080 to the trusted LAN in Windows Firewall.

Example llama.cpp server command (replace the model path with your merged/fine-tuned Qwen 7B GGUF):

```powershell
.\llama-server.exe -m "C:\models\qwen2.5-coder-7b-instruct-q4_k_m.gguf" --host 127.0.0.1 --port 8080 -ngl 99 -c 8192
```

Then run the backend and UI in two terminals:

```powershell
.\.venv\Scripts\uvicorn.exe apps.api.main:app --host 127.0.0.1 --port 8000
```

```powershell
npm run dev --prefix frontend -- --host 127.0.0.1 --port 5173
```

## Plan-aware training data

`model_training/data_v7_complex_plans/` documents the JSONL contract for QLoRA training examples. Each record contains a complex question, strict plan JSON, relevant schema, expected SQLite SQL or clarification, and optional failed-SQL repair context. Keep adapters, model weights, downloaded corpora, and generated outputs outside Git. Evaluate on at least 100 held-out real hard questions using execution success, result correctness, constraint coverage, clarification accuracy, and safety.
