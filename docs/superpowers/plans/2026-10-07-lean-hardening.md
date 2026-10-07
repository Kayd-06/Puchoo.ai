# Lean Platform Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Puchoo.ai's existing authentication, role-code collaboration, tenant isolation, local backup recovery, and delivery controls without adding product subsystems.

**Architecture:** Keep the existing `User` tenant fields and hashed `InstituteInvite` codes. Make invite expiry and member lifecycle explicit; use server-side session revocation for removal. Preserve ChromaDB's tenant/workspace filters and JWT HttpOnly cookies. Restore only local SQLite and Chroma backups into explicit empty development targets.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, SQLite, ChromaDB, pytest, Vite, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-07-platform-hardening-design.md`

## Global Constraints

- Do not add R2/S3/Supabase, pre-signed uploads, email invitations, organization tables, billing, Playwright, or account export/deletion APIs.
- Do not change the JWT HttpOnly-cookie or ChromaDB memory architecture.
- Do not persist or log credentials, JWTs, OTPs, recovery codes, or database passwords.
- Preserve existing uncommitted work; do not push.

### Task 1: Harden existing invite-code collaboration

**Files:**
- Create: `backend/alembic/versions/<revision>_invite_expiry.py`, `backend/tests/test_member_management.py`
- Modify: `backend/models.py`, `backend/routers/auth.py`, `backend/schemas.py`, `apps/api/security.py`, `apps/api/main.py`, `frontend/src/api/auth.js`, `frontend/src/components/workspace/WorkspaceInvitePanel.jsx`

- [ ] Write failing tests for expired invite rejection, owner/admin role update, removal revoking an active member session, and owner/member tenant isolation.
- [ ] Run the targeted tests and confirm they fail for the missing expiry/member APIs.
- [ ] Add `expires_at` to the existing invite record, enforce seven-day expiry during signup, and expose only member-management routes required by the current shared-workspace UI.
- [ ] Revoke removed members' sessions and login challenges atomically; never let a caller alter/remove an owner.
- [ ] Update the existing invite UI only for expiry/member actions, then run targeted backend tests and frontend lint/build.

### Task 2: Authorization matrix and documentation

**Files:**
- Create: `docs/permissions.md`, `backend/tests/permissions_matrix.py`, `backend/tests/test_authorization_matrix.py`
- Modify: router tests only if a matrix case proves a missing server-side guard.

- [ ] Write a route/role matrix for current routes only.
- [ ] Add parameterized integration tests proving 401 unauthenticated, 403 denied same-tenant, and 404 foreign-tenant behavior where a resource ID is accepted.
- [ ] Run the matrix tests and apply only demonstrated authorization corrections.

### Task 3: Backup restore and runbook

**Files:**
- Create: `docs/runbooks/backups.md`, `scripts/restore_latest_backup.py`, `tests/unit/test_restore_backup.py`
- Modify: `.env.example`, `backend/.env.example`, `README.md`

- [ ] Write failing tests for latest-backup selection, nonempty target refusal, unsafe production-like target refusal, SQLite restore, and separate Chroma target restore.
- [ ] Implement a SQLite/Chroma-only restore command that requires explicit empty targets and reports only counts/status.
- [ ] Document daily snapshots, 35-day retention, access/encryption responsibility, and a restore drill.
- [ ] Run the restore drill tests using temporary paths only.

### Task 4: Required reviews, dependency controls, and CI

**Files:**
- Create: `docs/testing.md`, `docs/security/threat-model.md`, `docs/reviews/performance.md`, `docs/reviews/test-quality.md`, `docs/reviews/security.md`, `docs/reviews/dependencies.md`, `.github/dependabot.yml`, `.github/workflows/ci.yml`
- Modify: dependencies only when a compatible, evidenced security upgrade is necessary.

- [ ] Inventory current routes, query boundaries, external calls, logs, and skipped tests.
- [ ] Write evidence-backed threat, performance, test-quality, and security reviews; do not add report-only features or silently remediate security findings.
- [ ] Run Python/npm dependency audits, document findings and reachability, add Dependabot, and configure CI for backend tests plus frontend lint/build.
- [ ] Apply only high-severity, directly used fixes with a failing regression test first.

### Task 5: Final verification and fresh review

- [ ] Run the full backend suite, frontend lint/build, restore tests, and a clean-process health request.
- [ ] Have a fresh reviewer inspect only the changed collaboration, authorization, restore, configuration, and logging paths.
- [ ] Report all findings, verification evidence, deferred R2 work, and deployment actions without pushing.
