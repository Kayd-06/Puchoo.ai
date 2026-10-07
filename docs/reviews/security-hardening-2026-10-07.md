# Security hardening report — 2026-10-07

## Scope

This review covers the security controls actually used by Puchoo.si: FastAPI,
JWT-backed HttpOnly session cookies, relational account storage, Chroma chat
memory, local CSV/Excel/SQLite imports, optional Sarvam language APIs, and the
React frontend. Cloudflare and distributed infrastructure were intentionally
left out for later deployment work.

## Implemented controls

### Abuse controls

- Authentication attempts are keyed by both client IP and normalized account
  email. Once a threshold is reached, temporary exponential backoff is used;
  accounts are not permanently locked.
- Public CSRF-cookie issuance has a moderate per-IP limit.
- Requests made through a verified session have a looser per-user limit.
- Database connection probes retain a stricter independent limit because they
  are expensive and interact with remote hosts.
- All thresholds and windows are environment settings:
  `AUTH_RATE_LIMIT`, `AUTH_RATE_WINDOW_SECONDS`,
  `AUTH_BACKOFF_BASE_SECONDS`, `AUTH_BACKOFF_MAX_SECONDS`,
  `PUBLIC_RATE_LIMIT`, `PUBLIC_RATE_WINDOW_SECONDS`,
  `AUTHENTICATED_RATE_LIMIT`, `AUTHENTICATED_RATE_WINDOW_SECONDS`,
  `CONNECTION_RATE_LIMIT`, and `CONNECTION_RATE_WINDOW_SECONDS`.
- The current store is thread-safe and in memory, which is appropriate for the
  current single-process deployment. Before running multiple API instances,
  replace it with a shared atomic store such as Redis.

### Input boundaries

- Auth, connection, query, execution, guardrail, profile, and translation
  request models reject unknown fields and enforce relevant types, formats,
  lengths, numeric ranges, or identifier patterns.
- Email values are validated and normalized. Password input is bounded before
  hashing. OTP, invite-role, and language-code formats are constrained.
- Upload count and byte thresholds are configurable with `UPLOAD_MAX_FILES`
  and `UPLOAD_MAX_BYTES`.

### File uploads

- Multipart files are read only up to the configured limit plus one byte, so an
  oversized upload cannot be fully buffered into memory.
- SQLite, XLSX, XLS, WAV, WebM, OGG, and MP3 inputs require the expected binary
  signature. CSV input must be non-empty UTF-8 text without NUL bytes and is
  rejected when it is HTML/XML content disguised as CSV.
- Only the formats used by the application are accepted. Parser errors are
  returned as generic messages.
- Original spreadsheet uploads are converted to generated SQLite files under
  the private `.pucho` runtime directory. SQLite uploads receive generated
  server-side names. This directory is ignored by Git and is never mounted as
  static web content; uploaded bytes are not executed as code.

### Error handling

- Unexpected exceptions are logged server-side with traceback context and
  returned to clients as a generic JSON 500 response.
- Sarvam, query generation/execution, upload, schema, metrics, and table
  inspection routes no longer echo raw provider, filesystem, database, or
  model exceptions.
- Authentication enumeration responses remain generic.

### Credentials and client exposure

- The tracked worktree and all reachable Git history were scanned for common
  cloud/API token and private-key signatures; no matches were found.
- `.env` and `backend/.env` are ignored. Only empty values or documented
  placeholders exist in example environment files.
- No frontend source references secret-like `VITE_`, `process.env`, or
  `import.meta.env` variables.
- Production startup already refuses the shipped development session and OTP
  secrets.

### Dependency controls

- `pip-audit -r requirements.txt`: no known vulnerabilities reported.
- `npm audit --omit=dev --audit-level=high`: zero vulnerabilities reported.
- CI runs backend tests, `pip-audit`, frontend lint/build, and the npm audit.
- Dependabot is configured for Python, npm, and GitHub Actions updates.

## Verification evidence

- Backend: `223 passed, 6 skipped`.
- Focused authentication/rate-limit suite: `40 passed`.
- Request/upload/error focused suite: passed.
- Frontend ESLint: passed.
- Frontend production build: passed.
- `git diff --check`: passed.

Warnings are dependency deprecations from FastAPI/TestClient, Chroma/Pydantic,
and httpx test cookie APIs; they do not represent test failures but should be
removed during routine dependency maintenance.

## Operational follow-up

- Keep real credentials only in the deployment secret store and rotate any
  credential if it has ever been shared outside that store, even though the Git
  signature scan is clean.
- Run the documented backup command on a schedule and periodically perform the
  isolated restore drill. The restore script and safety behavior are covered by
  automated tests; this session did not access a production backup.
- Add Cloudflare/WAF controls when the deployment is ready, as previously
  deferred.
- A source review and automated audits reduce risk but do not replace an
  independent penetration test before handling regulated or high-value data.
