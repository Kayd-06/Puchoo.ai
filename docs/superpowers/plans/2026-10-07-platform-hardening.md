# Platform Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable organization membership, privacy operations, recoverable backups, evidence-based assurance artifacts, and release automation without changing the current JWT-cookie or ChromaDB architecture.

**Architecture:** Organization membership becomes the durable authorization source while the existing workspace session manager remains runtime-only. Authorization resolves a caller’s membership before accessing a workspace; all Chroma operations keep tenant/workspace filters. Backup and privacy operations are explicit, least-privilege commands/endpoints with no credential or token export.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, SQLite/PostgreSQL, ChromaDB, pytest, React/Vite, GitHub Actions, Dependabot.

**Spec:** `docs/superpowers/specs/2026-10-07-platform-hardening-design.md`

## Global Constraints

- Defer Cloudflare/R2, pre-signed URLs, and changes to direct workspace upload/download flows.
- Keep account JWTs in HttpOnly, `SameSite=Lax` cookies and use server-side session revocation.
- Do not export, persist, or log passwords, JWTs, cookies, OTPs, recovery codes, invitation tokens, or database-connection secrets.
- Every schema change is an Alembic migration; all organization/resource lookups are tenant scoped.
- Security-review findings are reported before remediation unless separately approved.
- Preserve existing uncommitted work and do not push.

## Review Focus

- An invitation token accepted by a different email must fail without revealing invitation state.
- Removing a member must invalidate an already-issued cookie on the next request.
- An owner transfer must not leave zero owners after concurrent or repeated requests.
- A personal-account deletion must remove only its own Chroma metadata/documents, never another tenant’s.
- Restore tooling must reject a production or nonempty destination before writing data.

### Task 1: Organization schema and membership service

**Files:**
- Create: `backend/alembic/versions/<revision>_organizations.py`
- Modify: `backend/models.py`, `apps/api/security.py`, `backend/routers/auth.py`, `backend/schemas.py`
- Create: `backend/organizations.py`
- Test: `backend/tests/test_organizations.py`

**Interfaces:**
- Produces `Organization`, `OrganizationMember`, `OrganizationInvitation`, `membership_for_user()`, and `require_organization_role()`.
- Consumed by workspace guards, team routes, privacy endpoints, and authorization tests.

- [ ] Write failing migration/model tests for legacy-user backfill, one owner per personal organization, and membership uniqueness.
- [ ] Run those tests and confirm they fail because organization entities do not exist.
- [ ] Implement models, migration, and a service that derives tenant identity and role from an active membership; preserve legacy fields only as a compatibility read path.
- [ ] Make workspace guards resolve the caller’s organization membership and return 404 for another organization’s workspace.
- [ ] Run `pytest backend/tests/test_organizations.py backend/tests/test_role_access.py -q` and confirm passing.

### Task 2: Email invitation and member lifecycle APIs

**Files:**
- Modify: `backend/routers/auth.py`, `backend/emailer.py`, `backend/schemas.py`, `backend/organizations.py`, `apps/api/security.py`
- Create: `apps/api/routers/organizations.py`, `backend/tests/test_organization_members.py`
- Modify: `apps/api/main.py`, `frontend/src/api/auth.js`, `frontend/src/components/workspace/WorkspaceInvitePanel.jsx`, `frontend/src/pages/Settings.jsx`

**Interfaces:**
- Consumes Task 1 membership service.
- Produces authenticated endpoints for invite, accept, list members, role update, removal, ownership transfer, and leave.

- [ ] Write failing integration tests for 7-day expiry, normalized-email binding, one-time token use, 401/403/404 semantics, last-owner protection, role changes, transfer, leave, and session revocation on removal.
- [ ] Run the targeted tests and confirm they fail before the routes exist.
- [ ] Implement a hashed, single-use invitation token sent by email; require the recipient’s verified email on acceptance.
- [ ] Implement lifecycle routes with one transaction for membership change plus session/login-challenge revocation; use 409 for invalid ownership transitions.
- [ ] Replace the UI’s shareable role-code flow with email invite/member controls and role-aware actions.
- [ ] Run the targeted tests, `npm --prefix frontend run lint`, and `npm --prefix frontend run build`.

### Task 3: Matrix-derived authorization tests and permissions documentation

**Files:**
- Create: `docs/permissions.md`, `backend/tests/permissions_matrix.py`, `backend/tests/test_authorization_matrix.py`
- Modify: `backend/tests/conftest.py`, affected router tests only where a missing guard is proven.

**Interfaces:**
- Consumes roles/operations from Task 1 and route behavior from Task 2.
- Produces one machine-readable permission matrix used by parameterized integration tests.

- [ ] Write the permissions matrix first, including every API route’s authentication, organization scope, and minimum role.
- [ ] Implement test fixtures that create two organizations and execute matrix cases for unauthenticated (401), denied same-org (403), and foreign-org resource (404) behavior.
- [ ] Run `pytest backend/tests/test_authorization_matrix.py -q` and fix only server-side authorization defects it demonstrates.
- [ ] Run all backend authorization/role tests and document any intentionally public route exception.

### Task 4: Account data export and deletion

**Files:**
- Modify: `apps/core/chat_memory.py`, `backend/models.py`, `backend/routers/auth.py`, `backend/schemas.py`, `frontend/src/api/auth.js`, `frontend/src/pages/Settings.jsx`
- Create: `backend/privacy.py`, `backend/tests/test_account_privacy.py`

**Interfaces:**
- Produces `export_account_data(user_id)` and `delete_personal_account(user_id)` with scoped Chroma helpers.

- [ ] Write failing tests proving export excludes secrets, a member cannot delete an organization, deletion revokes current sessions, and Chroma deletion/export cannot cross tenant/workspace filters.
- [ ] Run them to demonstrate missing behavior.
- [ ] Add Chroma methods that enumerate/delete only metadata matching a supplied tenant/user scope; preserve the existing scoped memory methods.
- [ ] Implement authenticated JSON export and account deletion routes, requiring current-password confirmation for deletion and rejecting organization-owner deletion until ownership is transferred or the organization is explicitly dissolved.
- [ ] Add settings UI affordances with destructive-action confirmation and run the targeted backend tests plus frontend lint/build.

### Task 5: Backup runbook and safe restore drill

**Files:**
- Create: `docs/runbooks/backups.md`, `scripts/restore_latest_backup.py`, `tests/unit/test_restore_backup.py`
- Modify: `.env.example`, `backend/.env.example`, `README.md`

**Interfaces:**
- Produces `restore_latest_backup.py --backup-dir --target-database --target-chroma-dir`.

- [ ] Write failing unit tests for production-destination rejection, nonempty-target rejection, latest-backup selection, SQLite restore, and Chroma copy isolation.
- [ ] Implement a command that detects SQLite/PostgreSQL artifacts, requires explicit empty targets, refuses URLs/paths identified as production, and validates the restored relational store and Chroma directory without printing data.
- [ ] Document daily backups, 35-day retention, encryption/access expectations, PostgreSQL point-in-time recovery, Chroma snapshot handling, and an actual restore-drill checklist.
- [ ] Run restore tests against temporary SQLite and Chroma directories; never invoke a production database.

### Task 6: Evidence-based reviews and test strategy

**Files:**
- Create: `docs/testing.md`, `docs/security/threat-model.md`, `docs/reviews/performance.md`, `docs/reviews/test-quality.md`, `docs/reviews/security.md`
- Test: existing backend/frontend suites as evidence.

- [ ] Inventory every FastAPI route, SQLAlchemy query, raw SQL boundary, external request, input parser, log path, and skipped test.
- [ ] Write the threat model with assets, entry points, trust boundaries, OWASP risks, likelihood/impact, present controls, and gaps.
- [ ] Write the performance table containing file, line, evidence, severity, and precise remediation; apply only evidence-backed high-severity corrections after a dedicated failing regression test.
- [ ] Write the test strategy and quality review; distinguish external-provider mocks from database/auth behavior, and document Playwright critical flows plus the current absence of billing.
- [ ] Write the independent security report with file/line, severity, exploit scenario, and recommended fix; do not remediate report-only findings in this task.

### Task 7: Dependency security and CI

**Files:**
- Create: `.github/dependabot.yml`, `.github/workflows/ci.yml`
- Modify: `requirements.txt`, `frontend/package.json`, `frontend/package-lock.json`, `README.md`

**Interfaces:**
- CI runs Python tests, frontend lint/build, dependency audits, and Playwright when configured.

- [ ] Run Python and npm vulnerability audits; record package, advisory/severity, reachable code-path assessment, and safe upgrade decision in `docs/reviews/dependencies.md`.
- [ ] Write failing CI-config validation checks where practical, then add Dependabot and pinned CI jobs.
- [ ] Upgrade only compatible dependencies with passing project tests; explain deferred upgrades in the dependency report.
- [ ] Add Playwright tooling and critical sign-up/login/team-invite smoke flows only after backend fixture support exists; otherwise make the CI job explicitly non-blocking and document the prerequisite.
- [ ] Run the full backend suite, frontend lint/build, dependency audit commands, and a TestClient health request.

### Task 8: Final integration and independent review

**Files:**
- Modify: only files required by findings from Tasks 1–7.
- Test: full project suites and fresh-review report.

- [ ] Re-read the permissions matrix against every implemented endpoint and validate the final migration chain.
- [ ] Run the complete backend suite, frontend lint/build, restore drill, and app health request from a clean process.
- [ ] Have a fresh reviewer inspect authorization, Chroma isolation, deletion, restore safety, and configuration/logging changes; address only verified defects with test-first fixes.
- [ ] Report applied changes, deferred R2 scope, audit findings, commands/results, and any deployment steps without pushing.
