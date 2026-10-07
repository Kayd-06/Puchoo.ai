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
| `SMTP_FROM` | A verified `no-reply@your-domain` sender. Configure SPF, DKIM, and DMARC with the SMTP provider to keep OTPs out of spam. |

### Run the app (frontend + backend)

Install the Python and frontend dependencies once, then open **two terminals at the
repository root**. These project commands work on macOS, Linux, and Windows:

```bash
# Terminal 1 — FastAPI backend at http://127.0.0.1:8000
npm run dev:backend
```

```bash
# Terminal 2 — Vite frontend at http://localhost:5173
npm run dev:frontend
```

Open [http://localhost:5173](http://localhost:5173). The Vite development server
proxies `/api` requests to the backend on port 8000, so login, OTP, uploads, and
workspace APIs use the same origin.

If you prefer to start the services directly, use the matching commands below.

**macOS / Linux**

```bash
# Terminal 1
./.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

**Windows PowerShell**

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

Verify the backend independently with:

```bash
curl http://127.0.0.1:8000/api/health
```

Auth tests:

```powershell
.\venv\Scripts\python.exe -m pytest backend/tests -q
```

### How auth works

- `POST /api/v1/auth/signup` accepts `full_name`, `email`, `password`, `confirm_password`, and `workspace_type` (`personal` or `institute`). Institute workspaces also require `institute_name`. Email is stored in lowercase. Passwords need at least 10 characters, including a letter and a number, and are hashed with argon2. A duplicate email gets a generic error.
- `POST /api/v1/auth/login` checks the email and password. The error is always `Invalid email or password`. A correct password does not open a session yet. It emails a 6-digit code that expires in 10 minutes. `POST /api/v1/auth/login/verify` checks that code and then creates the session. SMTP uses `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, and `SMTP_PASSWORD`.
- A successful signup or login creates a signed JWT with a unique session ID (`jti`). The browser receives it only in an HttpOnly `puchoo_session` cookie with `SameSite=Lax` (and `Secure` when `COOKIE_SECURE=true`); React never receives or stores it. A SHA-256 hash of the JWT is bound to a server-side session record, so logout and revocation take effect immediately. Sessions last 7 days and rotate on authenticated requests.
- `POST /api/v1/auth/logout` revokes that session and clears the cookie. `GET /api/v1/auth/me` returns the current user, or 401.
- Changing an account email requires the current password, then a 6-digit OTP delivered to the new address. The address is updated only after `POST /api/v1/auth/email/change/verify` validates that OTP.
- State-changing auth requests need a double-submit CSRF token: the non-HttpOnly `csrf_token` cookie and the same value in the `X-CSRF-Token` header.
- Login and signup are limited to 5 attempts per 15 minutes for each IP and each email. The limit returns 429.
- Passwords and tokens are not written to logs.

### Approved conversation memory

When a user executes a proposed query, that action is treated as approval. Puchoo saves only the question, its interpretation, and verification summary to local persistent ChromaDB. It does not put result rows, generated SQL, connection strings, passwords, or tokens into vector memory. Every ChromaDB read/write is filtered by both the account/institute tenant and workspace ID; institute members can access their shared institute workspace, while personal workspaces remain private. The semantic recall endpoint is `GET /api/history/{workspace_id}/memory/search?q=...`.

The landing page is `/`. `/login` and `/signup` are the account forms. `/ask` is the signed-in workspace. Logged-in visitors are sent from the account forms to `/ask`.

To replace the final call-to-action image, add a file at `frontend/public/cta-visual.png`.

## Safe execution and verification

- A question is answered automatically only after its SQL passes the read-only guardrails and database query-plan validation.
- The execution boundary parses SQL with SQLGlot, accepts one `SELECT` only, rejects data-changing CTEs and multiple statements, and clamps the outermost `LIMIT`.
- No credentials or source data are stored in the React UI. The FastAPI layer maintains strict session and tenant boundaries.

## Configuration

Copy `.env.example` to a local, uncommitted `.env` when credentials are ready. The default SQL provider is the local MLX server, so it needs no model API key for basic SQL generation. Completed queries are verified with Anthropic when `ANTHROPIC_API_KEY` is configured; otherwise Puchoo automatically uses `GROQ_API_KEY` and `GROQ_VERIFIER_MODEL` (or `GROQ_MODEL`).

To enable voice input, set `SARVAM_API_KEY`. The microphone control records a short clip, and Sarvam auto-detects supported Indian languages and English. Puchoo keeps the transcript and executive answer in the detected language, translating internally only for the English SQL planner.

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

Start Puchoo with the two commands in [Run the app (frontend + backend)](#run-the-app-frontend--backend).

## Plan-aware training data

`model_training/data_v7_complex_plans/` documents the JSONL contract for QLoRA training examples. Each record contains a complex question, strict plan JSON, relevant schema, expected SQLite SQL or clarification, and optional failed-SQL repair context. Keep adapters, model weights, downloaded corpora, and generated outputs outside Git. Evaluate on at least 100 held-out real hard questions using execution success, result correctness, constraint coverage, clarification accuracy, and safety.
