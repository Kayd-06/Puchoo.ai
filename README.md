# Puchoo.si

Puchoo.si is a multilingual analytics workspace built with React and FastAPI. Users connect a data source, ask a question by typing or speaking, and receive results from guarded read-only SQL. The public landing page includes a product walkthrough, language and Gnani sections, FAQs, and an interactive letterform footer.

**Submitting a question automatically runs guarded read-only SQL.** SQL inspection is available afterward through **View query**. No mandatory Run/Cancel or second approval UI is part of the normal flow. Verification is advisory: distinguish a verified result from a mismatch or unavailable verification.

## Requirements

- Python **3.11 or newer** and a virtual environment.
- Node.js **22 or newer**, with npm.
- SMTP access for account verification and recovery emails.
- Provider credentials for the features you enable; see [Configuration](#configuration).

Run commands from the repository root. CI currently checks Python 3.11 and Node.js 22.

## Local setup

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
npm ci --prefix frontend
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
npm ci --prefix frontend
```

Create `.env` only if it does not already exist; preserve existing local configuration. Set the required credentials in that uncommitted file. Never put provider keys in frontend variables or source files.

Open two terminals at the repository root:

```bash
# Terminal 1: FastAPI, http://127.0.0.1:8001
npm run dev:backend
```

```bash
# Terminal 2: Vite, http://localhost:5173
npm run dev:frontend
```

The backend launcher detects `.venv` (or the legacy Windows `venv` directory). On macOS/Linux it falls back to `python3` if `.venv` is absent. Backend startup applies Alembic migrations. For a manual migration with the virtual environment activated:

```bash
python -m alembic -c backend/alembic.ini upgrade head
```

Open [localhost:5173](http://localhost:5173). Vite proxies `/api` to `127.0.0.1:8001`. Port 8001 keeps Puchoo separate from other FastAPI projects on port 8000. To use another port, set `PUCHOO_API_PORT` to the same value in both terminal sessions before starting the servers. Restart Vite after changing the port. Check backend health with:

```bash
curl http://127.0.0.1:8001/api/health
```

To create the frontend production bundle:

```bash
npm --prefix frontend run build
```

The output is `frontend/dist`. A production host must serve SPA routes and forward `/api` requests to FastAPI; the Vite development proxy is not a production proxy.

## Configuration

Use `.env.example` as the configuration inventory. Backend configuration reads the root `.env`, then `backend/.env`; the latter wins for duplicate file values. Existing process environment variables take precedence over both files.

| Settings                                                                  | Purpose                                                                                                                                                                                         |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PUCHOO_SQL_PROVIDER`                                                     | `deepseek` by default; also supports `local` and `claude`. The removed `groq` provider is rejected.                                                                                             |
| `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_PLANNER_MODEL`            | Default hosted SQL generation/planning. The example model is `deepseek-flash`.                                                                                                                  |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_VERIFIER_MODEL`                           | Independent verification when configured. Otherwise verification falls back to DeepSeek, with optional `DEEPSEEK_VERIFIER_MODEL`.                                                               |
| `LOCAL_SQL_MODEL_URL`, `LOCAL_SQL_MODEL_NAME`, `LOCAL_SQL_REQUEST_STYLE`  | Local OpenAI-compatible model endpoint when `PUCHOO_SQL_PROVIDER=local`. Additional attempt, token, and schema limits are in `.env.example`.                                                    |
| `GNANI_API_KEY`                                                           | Gnani/Vachana speech transcription and spoken answers.                                                                                                                                          |
| `SARVAM_API_KEY`, `SARVAM_TRANSLATION_MODEL`                              | Text translation: questions to English, then answer text, labels, and cells back to the selected language. Sarvam does not handle speech.                                                       |
| `DATABASE_URL`                                                            | Application accounts, workspace metadata, and history. Defaults to SQLite at `backend/puchoo_auth.db`; PostgreSQL is also supported.                                                            |
| `FRONTEND_ORIGINS`                                                        | Allowed frontend origins; local defaults include `localhost:5173` and `127.0.0.1:5173`.                                                                                                         |
| `JWT_ISSUER`                                                              | JWT issuer; defaults to `puchoo.si`. Changing it invalidates existing session cookies.                                                                                                          |
| `SESSION_SECRET`, `OTP_SECRET`                                            | Session signing and OTP protection. Replace all shipped placeholders.                                                                                                                           |
| `ENVIRONMENT`, `COOKIE_SECURE`                                            | Production requires `ENVIRONMENT=production`, `COOKIE_SECURE=true`, HTTPS, and non-default secrets.                                                                                             |
| `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Delivery of signup/login verification and recovery emails. Set an authorized `SMTP_FROM` mailbox unless `SMTP_USERNAME` is already a mailbox; there is no hardcoded fallback sender domain.     |
| `SMTP_USE_TLS`, `SMTP_USE_SSL`                                            | STARTTLS (usually port 587) or implicit TLS (usually 465); enable only one. TLS validates certificates and server identity.                                                                     |
| `ALLOWED_DB_HOSTS`                                                        | Explicitly allowed private/loopback database destinations. Leave empty unless intentionally connecting to one.                                                                                  |
| `DB_SSL_REQUIRED`, `DB_SSL_ROOT_CERT`, `DB_SSL_CA`                        | Workspace database TLS and trusted CA bundles. PostgreSQL uses hostname-verifying `verify-full`; legacy accepted `DB_SSL_MODE` values normalize to it. MySQL verifies certificate identity too. |

A selected hosted SQL provider without its required credentials returns a configuration error for model-dependent questions. English typed questions do not need the speech/translation providers. Non-English queries need translation configured; voice and spoken playback need Gnani.

### Data flow and persistence

- The configured SQL model receives the question and a selected schema summary. Verification can send SQL and up to 50 result rows to the verifier provider.
- Gnani receives recorded audio or answer text requested for playback. Sarvam receives text requested for translation.
- Persistent Chroma memory stores scoped question/interpretation/verification context, excluding result rows, generated SQL, connection strings, and secrets. Retrieval is filtered by tenant and workspace; it remains untrusted background for fresh queries.
- Relational history and browser chat state can retain displayed results. Clearing the visible chat and deleting saved history are separate actions.
- Server database credentials remain in process memory; server sources require reconnection after restart.
- Runtime state lives under configured paths, including the application database and `.pucho`. Keep these private and outside the served frontend directory.

## Responsive interface

Phone and tablet layouts below 1024px use a workspace drawer for navigation and active-source switching. Larger screens retain the sidebar. Account forms, settings, source connections, and results reflow for narrow screens; wide query tables scroll within their result cards. Touch controls, keyboard focus handling, and safe-area spacing support compact devices without changing role permissions.

## Accounts and roles

Signup and login use email verification before opening an authenticated session. Sessions use signed JWTs in HttpOnly cookies with server-side revocation; the frontend does not store session tokens in local storage. State-changing requests require the CSRF cookie/header pair. API authorization remains authoritative regardless of UI visibility.

| Role          | Access                                                                                                           |
| ------------- | ---------------------------------------------------------------------------------------------------------------- |
| Owner / admin | Manage data sources, guardrails, invite codes and members; ask questions and review history.                     |
| Editor        | Ask questions, inspect SQL/results, and review shared history; cannot upload or administer data sources/members. |
| Viewer        | Review shared history/results and manage their own account; cannot submit queries or administer sources.         |

Foreign-tenant workspace resources return 404; insufficient same-tenant permissions return 403. Invalid or absent sessions return 401.

## Data sources and execution limits

Upload **CSV or XLSX** files, or connect a supported PostgreSQL/MySQL server. XLS and arbitrary SQLite database uploads are unsupported; export those tables as CSV/XLSX first. Only owners/admins can upload or manage sources. Tabular imports produce managed private SQLite datasets.

| Setting                              | Default / hard ceiling                                                |
| ------------------------------------ | --------------------------------------------------------------------- |
| `UPLOAD_MAX_FILES`                   | 10 files per request                                                  |
| `UPLOAD_MAX_BYTES`                   | 26,214,400 bytes per file (25 MiB)                                    |
| `UPLOAD_XLSX_MAX_UNCOMPRESSED_BYTES` | 33,554,432 bytes (32 MiB)                                             |
| `UPLOAD_XLSX_MAX_COMPRESSION_RATIO`  | 100                                                                   |
| `UPLOAD_MAX_SHEETS`                  | 50                                                                    |
| `UPLOAD_MAX_ROWS`                    | 1,000,000 per sheet/CSV                                               |
| `UPLOAD_MAX_COLUMNS`                 | 500                                                                   |
| `UPLOAD_MAX_CELLS`                   | 250,000 across all sheets/files                                       |
| `QUERY_STATEMENT_TIMEOUT_SECONDS`    | 15 seconds; workspace settings can only lower the configured ceiling  |
| `QUERY_MAX_ROWS`                     | 5,000 returned rows; capped results are flagged as truncated          |
| `PENDING_QUERY_TTL_SECONDS`          | 600 seconds; the UI normally consumes the execution token immediately |

Upload configuration can lower, but cannot raise, the parser's hard safety ceilings. Preflight checks reject oversized/unsupported content before full frame allocation.

SQLGlot validates read-only statements, functions, tables, and columns. System catalogs, writes, executable comments, and unsafe functions are rejected. Execution tokens bind the SQL to the authenticated actor, tenant, and workspace and are single-use. Failed queries may receive one guarded correction only when safety and semantic-preservation checks succeed.

Use dedicated read-only database accounts with access only to the intended tables. PostgreSQL, MySQL/MariaDB, and managed SQLite execution also enforce read-only modes, timeouts, and result limits.

## Backup and recovery

Run **one API process/worker**. Multi-process cache/state coordination and deployment recovery require separate validation.

The included offline backup supports a **SQLite application database**, its authority/deletion state, referenced managed uploaded SQLite datasets, and the paired Chroma directory. It excludes `.env`, server credentials, unreferenced uploads, and PostgreSQL servers. PostgreSQL authority requires a separately validated backup procedure.

Stop **all API, indexing, and maintenance writers** before creating a snapshot. Use the actual configured database, Chroma, and upload paths, with a trusted private backup destination outside the repository/web root:

```bash
python -m scripts.create_backup --database /srv/puchoo/auth.db \
  --chroma /srv/puchoo/chroma --uploads /srv/puchoo/uploads \
  --destination /secure/backups/2026-11-10T180000 --writers-stopped
```

Before restoring, reconcile the newest deletion/privacy ledger with the snapshot. Older snapshots cannot know about later deletions. The acknowledgement below records an operator review; it does not perform reconciliation. If evidence is unavailable, keep restored data offline until privacy review and any necessary purge/rebuild are complete.

```bash
python -m scripts.restore_latest_backup --backup-dir /secure/backups \
  --destination /srv/recovery/reviewed-2026-11-10 --acknowledge-privacy-review
```

The restore destination must not exist. Only versioned manifested snapshots qualify; corrupt latest snapshots do not silently fall back. After a successful restore, configure `DATABASE_URL` for `destination/auth.db`, `CHROMA_PATH` for `destination/chroma`, and `PUCHOO_UPLOAD_DIRECTORY` for `destination/datasets`. Verify startup, accounts, source scope, history, and deletion suppression before reconnecting users. Reconnect server sources manually.

Keep backups private, encrypted, access-controlled, and subject to a retention policy. Never delete a `.maintenance.lock` sidecar while a writer or backup may hold it; it can invalidate process coordination.

## Testing and repository layout

With the Python virtual environment activated:

```bash
python -m pytest -q
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run format:check
```

Some integration tests require the `TEST_AUTH_POSTGRES_URL` / `TEST_PERSISTENCE_POSTGRES_URL` variables and a disposable PostgreSQL database. TLS fixtures require OpenSSL and permission to bind loopback listeners. Tests use synthetic credentials; do not point fixtures at production services.

CI runs migration checks, Python tests, frontend tests/lint/build/formatting, and dependency audits. It currently retains documented Chroma HTTP-server advisory exceptions in `.github/workflows/ci.yml`; review those before release. Automated checks do not replace real-provider, mobile, deployment, or recovery validation.

| Path                      | Purpose                                                                               |
| ------------------------- | ------------------------------------------------------------------------------------- |
| `frontend/`               | React/Vite landing page, accounts, analytics UI, component tests, and assets.         |
| `backend/`                | FastAPI application, authentication, persistence, migrations, and integration tests.  |
| `apps/api/`, `apps/core/` | Product routes, query planning/execution, providers, guardrails, and memory.          |
| `tests/unit/`             | Python regression coverage for core logic and operational scripts.                    |
| `scripts/`                | Backend launcher, migrations, offline backup/restore, and Linux upload-budget probes. |
| `.github/`                | CI and dependency-update configuration.                                               |

Generated verification output under `reports/`, Python caches, dependencies, local environment files, and runtime data are ignored by Git. This README is the repository's consolidated setup and maintenance guide.

The presentation/video script is [gnani_script.md](gnani_script.md). Keep this file during repository cleanups.
