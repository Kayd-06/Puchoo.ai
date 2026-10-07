# Threat model

## Assets and boundaries

Protected assets are account records, password/OTP hashes, session state, workspace metadata, database connection credentials supplied at runtime, approved Chroma conversation memory, and uploaded datasets. The browser is untrusted. FastAPI is the authorization boundary; SQLite/PostgreSQL and Chroma are trusted persistence services; SMTP, LLM, and voice providers are external boundaries.

## Primary threats and controls

| Entry point | Threat | Likelihood / impact | Current control | Remaining action |
| --- | --- | --- | --- | --- |
| Auth and session cookies | credential stuffing, token theft, CSRF | medium / high | Argon2, rate limits, HttpOnly cookies, server-side token hashes, CSRF middleware | enforce secure cookies and non-default secrets in production |
| Invite-code signup | leaked/replayed shared code | medium / high | hashed codes, role scoping, rotation | seven-day expiry and revocation tests |
| Workspace/resource IDs | IDOR / tenant escape | medium / high | tenant owner guard, 404 behavior | matrix tests for every resource route |
| Server connection form | SSRF and credential exposure | medium / high | host validation, TLS policy, no password persistence | retain regression coverage |
| Query generation/execution | SQL injection or unsafe query | medium / high | SQLGlot guardrails, read-only executor | performance/security review before release |
| Chroma memory | cross-tenant disclosure | low / high | required tenant/workspace metadata filters | scope tests on every new operation |
| Backups | disclosure or destructive restore | medium / high | separate-target restore utility | encrypted restricted snapshot storage and restore drills |

Object storage is deferred and is not a current trust boundary.
