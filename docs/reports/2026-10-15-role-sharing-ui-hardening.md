# Role sharing and UI hardening release report

## Delivered behavior

- Owner and admin accounts can upload, connect, configure, and remove data sources; create role-specific invite codes; and view, change, or remove workspace members.
- Editors can query the tenant's existing data and review shared history, but data-source and member-administration controls are denied by the API and absent from navigation.
- Viewers can review shared history/results and account settings, but cannot query or administer data.
- The authenticated user contract now returns the effective `role`, `tenant_id`, and explicit capabilities used by the frontend.
- Tenant membership, workspace metadata, guardrails, and query history are persisted relationally and restored after restart. Server credentials are not persisted; server sources require reconnection after restart.
- Settings shows the signed-in role and supports profile images by device upload or HTTPS link for every role.
- Login verification, password reset, and email-change verification share an accessible OTP control.
- Decorative security claims and authenticated scan/glow treatments targeted by this release were removed. The settings surface uses the same neutral dark shell palette as the sidebar.

## Database and deployment

1. Back up the application database.
2. Deploy the backend and frontend from the same release.
3. Start the backend normally; `init_db()` upgrades through Alembic revision `20261015_0015` and backfills tenants/memberships from existing users.
4. Restart all backend workers so each process hydrates the same persisted workspace metadata.
5. Reconnect server data sources because credentials are intentionally memory-only.

## Verification evidence

- Backend: `pytest -q` — 543 passed, 10 skipped.
- Frontend: `npm --prefix frontend test -- --run` — 16 passed.
- Static checks: ESLint passed; Vite production build passed; `git diff --check` passed.
- Role-focused backend suites — 22 passed.
- Production npm dependency audit — 0 vulnerabilities.

CI now runs schema migration tests before the full backend suite, then frontend component tests, lint, build, Python audit, and production npm audit. Failure-only JUnit artifacts are retained.

## Known limits

- This environment exposed no controllable browser surface, so responsive browser automation could not be completed. Component-level DOM/accessibility checks, responsive CSS inspection, and the production build were completed instead.
- `pip-audit` was not installed in the local runtime. CI installs it and runs the repository's documented exceptions for Chroma HTTP-server advisories; this app embeds the local client and does not expose that server.
- Server connection secrets deliberately do not survive restart and must be entered again by an owner/admin.
