# Role Sharing and UI Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build persistent tenant sharing with an enforced owner/admin/editor/viewer permission matrix, role-aware account UI, reliable profile images and OTP flows, restrained visual styling, and blocking CI coverage.

**Architecture:** Add relational tenant, membership, workspace, guardrail, and history repositories behind a centralized capability policy. Preserve the existing query engine by resolving database records into its current internal workspace shape; retain runtime-only server credentials and mark unrecoverable sources unavailable after restart. Drive frontend navigation and controls from capabilities returned by `/auth/me`, while enforcing every permission again in FastAPI.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, React 19, React Router, Vite, Vitest, Testing Library, ESLint, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-14-role-sharing-and-ui-hardening-design.md`

## Global Constraints

- Owner/admin may upload, connect, delete, configure, invite, and manage members.
- Editor may query existing tenant data and view history, but may not upload, connect, delete, configure, invite, or manage members.
- Viewer may view shared history/results only.
- Every authenticated role may view account settings and manage its own profile image and verified email.
- Foreign-tenant resources return 404; in-tenant forbidden actions return 403.
- The browser never receives database credentials or arbitrary internal source paths.
- Keep the current query engine; replace only tenant/workspace lookup and persistence boundaries.
- Keep flat semantic badges; remove decorative security tags, glow sweeps, fake telemetry, and ornamental motion from authenticated screens.
- Support SQLite development and the configured production database.

## Review Focus

- A legacy owner with no membership row must be backfilled once and must not create duplicate tenants on repeated migration/startup; covered in Task 2.
- An editor that already has a stale Data Sources route open must receive 403 and a role-aware page after their role changes; covered in Tasks 3 and 4.
- A member whose tenant access is removed while their browser is open must lose the session and cached workspace selection; covered in Tasks 3 and 4.
- A server source without restorable credentials after restart must remain visible as unavailable without leaking connection data; covered in Task 2.
- Pasted OTP values containing spaces or non-digits must normalize safely without submitting twice; covered in Task 6.

---

### Task 1: Canonical Capabilities and Account Contract

**Files:**
- Create: `backend/authorization.py`
- Modify: `apps/api/security.py`
- Modify: `backend/schemas.py`
- Modify: `backend/routers/auth.py`
- Test: `backend/tests/test_role_access.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Produces: `EffectiveRole = Literal["owner", "admin", "editor", "viewer"]`.
- Produces: `capabilities_for(user: User) -> AccountCapabilities` with booleans `view_workspaces`, `view_history`, `query_workspace`, `manage_data_sources`, `administer_workspace`, and `manage_account`.
- Produces: `require_capability(name: CapabilityName)` FastAPI dependency factory.
- Produces: `UserResponse.role`, `UserResponse.tenant_id`, and `UserResponse.capabilities`.

- [ ] **Step 1: Write failing capability-contract tests**

Add parametrized tests asserting the exact six booleans for owner/admin/editor/viewer, and assert `/api/v1/auth/me` returns the effective role, canonical tenant ID, and capability object after login.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q backend/tests/test_role_access.py backend/tests/test_auth.py -k 'capabilit or effective_role'`

Expected: FAIL because the centralized policy and response fields do not exist.

- [ ] **Step 3: Implement the centralized policy and response contract**

Make `apps/api/security.py` delegate role/capability decisions to `backend.authorization`; retain temporary compatibility wrappers only for routes migrated in later tasks.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q backend/tests/test_role_access.py backend/tests/test_auth.py -k 'capabilit or effective_role'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/authorization.py apps/api/security.py backend/schemas.py backend/routers/auth.py backend/tests/test_role_access.py backend/tests/test_auth.py
git commit -m "feat: centralize account capabilities"
```

### Task 2: Persistent Tenant Workspace Repository

**Files:**
- Modify: `backend/models.py`
- Create: `backend/workspace_repository.py`
- Create: `backend/alembic/versions/20261015_0015_persist_tenant_workspaces.py`
- Modify: `apps/api/session.py`
- Modify: `apps/core/local_state.py`
- Test: `backend/tests/test_schema_upgrade.py`
- Create: `backend/tests/test_workspace_repository.py`

**Interfaces:**
- Produces SQLAlchemy models: `Tenant`, `TenantMembership`, `WorkspaceRecord`, `WorkspaceGuardrail`, `WorkspaceHistoryRecord`.
- Produces `WorkspaceRepository.list_for_tenant(tenant_id: str) -> list[dict]`.
- Produces `WorkspaceRepository.get_for_tenant(workspace_id: str, tenant_id: str) -> dict | None`.
- Produces `WorkspaceRepository.save_workspace(workspace: dict, tenant_id: str) -> dict` and persistence methods for guardrails/history.
- Produces `import_legacy_local_state(db: Session) -> LegacyImportResult`, idempotent by legacy workspace ID.

- [ ] **Step 1: Write failing repository and migration tests**

Cover legacy membership backfill, repeated import without duplication, same-tenant listing, foreign-tenant exclusion, history/guardrail persistence after a new SQLAlchemy session, and a server workspace returning `availability="unavailable"` after runtime credentials are cleared.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q backend/tests/test_workspace_repository.py backend/tests/test_schema_upgrade.py`

Expected: FAIL because the relational repository and migration do not exist.

- [ ] **Step 3: Add models, migration, repository, and legacy importer**

Use an opaque `source_ref` plus `source_type` and `availability`; never serialize server credentials. Backfill one tenant and owner membership per existing owner, then memberships for users with `workspace_owner_id`.

- [ ] **Step 4: Adapt `SessionManager` as a compatibility adapter**

Keep its public internal workspace shape for query code, but source persisted metadata/guardrails/history from `WorkspaceRepository`; runtime connection secrets remain process memory only.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `pytest -q backend/tests/test_workspace_repository.py backend/tests/test_schema_upgrade.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/workspace_repository.py backend/alembic/versions/20261015_0015_persist_tenant_workspaces.py apps/api/session.py apps/core/local_state.py backend/tests/test_schema_upgrade.py backend/tests/test_workspace_repository.py
git commit -m "feat: persist tenant workspace metadata"
```

### Task 3: Enforce the Confirmed Role Matrix End to End

**Files:**
- Modify: `apps/api/routers/workspaces.py`
- Modify: `apps/api/routers/query.py`
- Modify: `apps/api/routers/history.py`
- Modify: `apps/api/routers/settings.py`
- Modify: `apps/api/routers/sarvam.py`
- Modify: `backend/routers/auth.py`
- Modify: `docs/permissions.md`
- Test: `backend/tests/test_role_access.py`
- Test: `backend/tests/test_member_management.py`
- Test: `backend/tests/test_server_connections.py`
- Test: `backend/tests/test_workspace_upload.py`

**Interfaces:**
- Consumes: `require_capability(name)` and `WorkspaceRepository` from Tasks 1–2.
- Produces: every workspace route enforces the role matrix from the spec.
- Produces: invite redemption persists membership in the original tenant and role changes are immediately authoritative.

- [ ] **Step 1: Write the failing four-role integration matrix**

Create an owner plus admin/editor/viewer through real role codes. Assert all four list the same tenant workspaces; owner/admin upload and connect successfully; editor/viewer receive 403; editor query succeeds; viewer query receives 403; only owner/admin invite, delete, change guardrails, and manage members; a separate tenant receives 404 for those workspace IDs.

- [ ] **Step 2: Add restart and revocation failures**

Recreate the application/database session and assert memberships/workspaces remain visible. Change editor to viewer and assert the next query receives 403. Remove a member and assert their next `/auth/me` returns 401.

- [ ] **Step 3: Run tests and verify RED**

Run: `pytest -q backend/tests/test_role_access.py backend/tests/test_member_management.py backend/tests/test_server_connections.py backend/tests/test_workspace_upload.py`

Expected: FAIL because editors currently upload and workspace persistence is split.

- [ ] **Step 4: Replace route-specific role checks with capabilities and repository lookups**

Uploads and server connections require `manage_data_sources`; queries/schema require `query_workspace`; destructive/configuration/member/invite operations require `administer_workspace`; history reads require `view_history`.

- [ ] **Step 5: Update the permission document and run GREEN verification**

Run: `pytest -q backend/tests/test_role_access.py backend/tests/test_member_management.py backend/tests/test_server_connections.py backend/tests/test_workspace_upload.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/routers backend/routers/auth.py docs/permissions.md backend/tests/test_role_access.py backend/tests/test_member_management.py backend/tests/test_server_connections.py backend/tests/test_workspace_upload.py
git commit -m "fix: enforce tenant role boundaries"
```

### Task 4: Role-Aware Navigation, Settings, and Forbidden Routes

**Files:**
- Create: `frontend/src/auth/capabilities.js`
- Modify: `frontend/src/components/layout/Sidebar.jsx`
- Modify: `frontend/src/components/layout/TopBar.jsx`
- Modify: `frontend/src/pages/ConnectData.jsx`
- Modify: `frontend/src/pages/AskData.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/context/AppContext.jsx`
- Create: `frontend/src/test/setup.js`
- Create: `frontend/src/pages/__tests__/role-surfaces.test.jsx`
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.js`

**Interfaces:**
- Consumes: `user.role`, `user.tenant_id`, and `user.capabilities` from Task 1.
- Produces: `can(user, capability: string) -> boolean` with deny-by-default behavior.
- Produces: Settings account section for every role and admin panels only when `administer_workspace` is true.

- [ ] **Step 1: Add Vitest/Testing Library and write failing role-surface tests**

Add `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, and `@testing-library/user-event` as dev dependencies. Assert owner/admin see Data Sources and invite management; editor sees Ask Data/History/Settings but no Data Sources/upload/connect; viewer sees History/Settings and a limited account page; each role badge displays its exact role. Test a stale editor ConnectData render after role downgrade shows the forbidden state and no file input.

- [ ] **Step 2: Run tests and verify RED**

Run: `npm --prefix frontend test -- --run src/pages/__tests__/role-surfaces.test.jsx`

Expected: FAIL because UI logic is based on viewer-only checks and viewers receive a blocked Settings page.

- [ ] **Step 3: Implement capability-driven surfaces**

Do not infer permissions from route names or duplicate the role matrix. Clear `pucho_active_workspace` when refreshed workspaces no longer contain the selection or the session becomes unauthorized.

- [ ] **Step 4: Run tests, lint, and build**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run lint && npm --prefix frontend run build`

Expected: all commands PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/auth frontend/src/components/layout frontend/src/pages frontend/src/context/AppContext.jsx frontend/src/test frontend/package.json frontend/package-lock.json frontend/vite.config.js
git commit -m "feat: render role-aware product surfaces"
```

### Task 5: Finish Persistent Profile Images for Every Role

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/schemas.py`
- Modify: `backend/routers/auth.py`
- Modify: `backend/alembic/versions/20261014_0014_add_profile_image.py`
- Modify: `backend/tests/test_auth.py`
- Modify: `frontend/src/api/auth.js`
- Modify: `frontend/src/context/AuthContext.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/components/layout/TopBar.jsx`
- Modify: `frontend/src/pages/__tests__/role-surfaces.test.jsx`

**Interfaces:**
- Produces: `PUT /api/v1/auth/profile-image` accepting `https://` or PNG/JPEG/WebP/GIF data URLs up to 1,500,000 characters, with `null` removing the image.
- Produces: `AuthContext.updateProfileImage(imageUrl: string | null)`.

- [ ] **Step 1: Reconcile the existing working-tree implementation with failing tests**

Retain tests proving persistence across `/auth/me`, unsafe URL rejection, removal, oversize rejection, and availability to admin/editor/viewer accounts. Add frontend tests for upload/link controls on every role and avatar propagation to the top bar.

- [ ] **Step 2: Run tests and verify failures cover remaining gaps**

Run: `pytest -q backend/tests/test_auth.py -k profile_image && npm --prefix frontend test -- --run src/pages/__tests__/role-surfaces.test.jsx`

Expected: backend persistence tests pass from the current working tree; new role/UI cases fail until Settings is capability-based.

- [ ] **Step 3: Complete the UI integration without duplicating account state**

Use `AuthContext.user` as the single image source and retain the current image on failed saves.

- [ ] **Step 4: Run GREEN verification and commit**

Run: `pytest -q backend/tests/test_auth.py -k profile_image && npm --prefix frontend test -- --run`

Expected: PASS.

```bash
git add backend/models.py backend/schemas.py backend/routers/auth.py backend/alembic/versions/20261014_0014_add_profile_image.py backend/tests/test_auth.py frontend/src/api/auth.js frontend/src/context/AuthContext.jsx frontend/src/pages/Settings.jsx frontend/src/components/layout/TopBar.jsx frontend/src/pages/__tests__/role-surfaces.test.jsx
git commit -m "feat: persist profile images for every role"
```

### Task 6: Shared Accessible OTP Experience

**Files:**
- Create: `frontend/src/components/auth/OtpInput.jsx`
- Create: `frontend/src/components/auth/__tests__/OtpInput.test.jsx`
- Modify: `frontend/src/pages/Login.jsx`
- Modify: `frontend/src/pages/Signup.jsx`
- Modify: `frontend/src/pages/ForgotPassword.jsx`
- Modify: `frontend/src/components/auth/ChangeEmailPanel.jsx`
- Modify: `frontend/src/components/auth/AuthShell.jsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: `OtpInput({ value, onChange, error, disabled, id, autoFocus })` with one accessible numeric input rendered as six visual cells.
- Produces: shared copy/states for expiry, resend cooldown, invalid/locked errors, and pending submissions.

- [ ] **Step 1: Write failing component tests**

Test typing, full-code paste, normalization of `" 12a 3456 "` to `"123456"`, backspace, accessible label/error association, disabled behavior, and one submit from one completed code.

- [ ] **Step 2: Run tests and verify RED**

Run: `npm --prefix frontend test -- --run src/components/auth/__tests__/OtpInput.test.jsx`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement and integrate the shared component**

Keep server challenge timing authoritative; client countdown is guidance. Preserve current rate-limit and challenge-expiry messages.

- [ ] **Step 4: Run tests, lint, and build**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run lint && npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/auth frontend/src/pages/Login.jsx frontend/src/pages/Signup.jsx frontend/src/pages/ForgotPassword.jsx frontend/src/index.css
git commit -m "fix: unify accessible OTP screens"
```

### Task 7: Remove Decorative Glow and Fake Status Treatments

**Files:**
- Modify: `frontend/src/components/layout/TopBar.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/pages/History.jsx`
- Modify: `frontend/src/pages/AskData.jsx`
- Modify: `frontend/src/pages/ConnectData.jsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/styles/site.css`
- Create: `frontend/src/__tests__/visual-semantics.test.jsx`

**Interfaces:**
- Consumes: approved visual direction A from the spec.
- Produces: flat semantic role/status badges and no decorative security labels or authenticated-screen glow animations.

- [ ] **Step 1: Write failing semantic UI tests and a CSS guard test**

Assert authenticated screens omit `Tenant isolated`, `HttpOnly session`, and `Guardrails active`. Scan authenticated CSS selectors for the removed scan/pulse animation names and glow-only pseudo-elements while allowing focus rings, error/success colors, and functional loading spinners.

- [ ] **Step 2: Run tests and verify RED**

Run: `npm --prefix frontend test -- --run src/__tests__/visual-semantics.test.jsx`

Expected: FAIL because decorative tags and animations remain.

- [ ] **Step 3: Remove ornamental markup/styles and normalize semantic badges**

Do not remove real loading, recording, validation, focus, or reduced-motion behavior. Preserve the marketing site's meaningful demonstration motion unless it presents fake product status.

- [ ] **Step 4: Run frontend verification and responsive browser QA**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run lint && npm --prefix frontend run build`

Expected: PASS. Manually verify login OTP, owner Settings, editor Ask Data, viewer History/Settings at 390px, 768px, and 1440px widths.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/TopBar.jsx frontend/src/pages frontend/src/index.css frontend/src/styles/site.css frontend/src/__tests__/visual-semantics.test.jsx
git commit -m "style: remove decorative product glow"
```

### Task 8: CI, Legacy Test Cleanup, and Release Verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Delete: `tests/ui/test_streamlit_mvp.py`
- Modify: `docs/testing.md`
- Test: all active backend and frontend suites.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: a CI pipeline that blocks on migrations, backend tests, role/UI tests, lint, build, and dependency audits.

- [ ] **Step 1: Replace obsolete Streamlit assertions with active React coverage**

Remove only tests whose referenced `apps/ui` files no longer exist; document their replacement by the Vitest role, OTP, and visual-semantic suites.

- [ ] **Step 2: Add explicit CI stages**

Run `pytest backend/tests/test_schema_upgrade.py --junitxml=reports/migrations.xml` before `pytest --junitxml=reports/backend.xml`, then run `npm --prefix frontend test -- --run --reporter=junit --outputFile=../reports/frontend.xml` before lint/build. Retain Python/npm audits and upload `reports/` only when a job fails.

- [ ] **Step 3: Run complete local verification**

Run:

```bash
pytest -q
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
```

Expected: all commands PASS with no missing-file Streamlit failures.

- [ ] **Step 4: Run the end-to-end role matrix against a temporary database**

Create owner/admin/editor/viewer through invite codes, verify the exact navigation/actions and shared workspace list, restart the backend, and repeat visibility/denial checks.

- [ ] **Step 5: Update testing documentation and commit**

```bash
git add .github/workflows/ci.yml tests/ui/test_streamlit_mvp.py docs/testing.md
git commit -m "ci: gate tenant roles and active frontend"
```

### Task 9: Whole-Feature Review and Handoff

**Files:**
- Review all files changed by Tasks 1–8.

**Interfaces:**
- Consumes: the completed implementation and spec.
- Produces: evidence-backed release report with migrations, tests, known limits, and deployment steps.

- [ ] **Step 1: Compare the final diff line-by-line with the role matrix and spec**

- [ ] **Step 2: Run the complete verification commands from Task 8 on the final tree**

- [ ] **Step 3: Inspect the live owner, admin, editor, and viewer flows in a browser**

- [ ] **Step 4: Report changed behavior, migration requirements, verification counts, and any remaining blocker**
