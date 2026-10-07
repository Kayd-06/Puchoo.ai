# Platform Hardening and Team Operations Design

## Scope and decisions

This design implements the requested platform hardening except object storage. Cloudflare/R2, pre-signed upload/download URLs, and migration of the current server-streamed workspace uploads are explicitly deferred until storage credentials and a provider choice are available.

### Binding scope amendment: lean implementation

This amendment replaces the feature-expansion parts of the design. Harden only Puchoo.ai features that already exist: JWT-cookie authentication, ChromaDB conversation memory, role-code workspace sharing, FastAPI API routes, local workspace uploads, and the relational account database. Do not add organization tables, email invitations, billing, Playwright, account export/deletion APIs, or a new object-storage integration.

Keep `workspace_owner_id`, `workspace_role`, and hashed `InstituteInvite` codes as the tenancy/collaboration model. Add only an expiry to those existing codes plus minimal member-role/removal controls needed to operate the existing shared-workspace feature. A removed member's sessions and login challenges must be revoked. The backup/restore tool is limited to the current SQLite database and Chroma persistence directory; PostgreSQL recovery remains deployment documentation only.

The application keeps its current identity and memory architecture:

- FastAPI remains the authorization boundary.
- JWTs remain HttpOnly, `SameSite=Lax` cookies; React never receives a bearer token.
- Server-side session records remain the revocation mechanism.
- ChromaDB remains approved-conversation memory, scoped by tenant/workspace.
- The existing relational database remains the source of truth for accounts, memberships, invitations, sessions, notifications, and audit-relevant data.

Production backup tooling supports PostgreSQL when `DATABASE_URL` is PostgreSQL and local SQLite for development. It also includes the configured Chroma persistence directory. The runbook sets a daily schedule and 35-day retention as an operational default; deployment automation may use a stricter policy.

No billing or upgrade-plan implementation exists in this product. Testing documentation will call that flow out as not applicable rather than inventing a payment system.

## Tenant and team model

The existing owner-id fields are insufficient for email invitations, membership lifecycle, and ownership transfer. Introduce explicit `Organization`, `OrganizationMember`, and `OrganizationInvitation` records while migrating current institution workspaces without breaking personal workspaces.

- A personal account has one private organization with one owner.
- An institution workspace maps to one organization and role-bearing members.
- Roles are `owner`, `admin`, `editor`, and `viewer`; permissions are documented in `docs/permissions.md` and consumed by authorization tests.
- Invitations are addressed to a normalized email, store only a token hash, expire after seven days, are single-use, and are accepted only by that email.
- Only owners can transfer ownership; the last owner cannot leave or be removed.
- Removal revokes every active session and login challenge for that member before returning success.
- Cross-organization resource lookup returns 404; an in-organization user lacking the required role receives 403.

## API and user-facing behavior

Add organization management endpoints for member listing, invitation creation/acceptance, role change, member removal, ownership transfer, and self-leave. Existing invite-code compatibility routes can remain temporarily but must be marked deprecated and use the same authorization service.

Add authenticated account-data export and account deletion endpoints. Export is a downloadable JSON response generated from the caller's relational records and tenant/workspace Chroma records, never credentials, password hashes, OTPs, session tokens, or raw database connection passwords. Deletion revokes sessions, deletes/anonymizes account-owned relational records according to foreign-key relationships, deletes the caller's personal Chroma records, and never permits a member to delete an organization owned by someone else.

The existing direct workspace-upload endpoints remain in place until object storage is selected. Their current server-streaming design is documented as deferred, not represented as a pre-signed-upload implementation.

## Data protection and backups

Passwords, one-time codes, recovery codes, session tokens, and invitation tokens are stored only as hashes. Database connection passwords are never persisted. Logs use stable error classes and redact credentials, cookies, authorization headers, tokens, emails where not necessary for operations, and query strings containing secrets.

Create a backup/restore command that:

1. refuses a production destination;
2. restores into a caller-supplied empty database name/path only;
3. restores relational data and Chroma data to separate timestamped targets;
4. verifies the restored database can open and reports object counts without exposing rows or secrets.

`docs/runbooks/backups.md` defines schedule, retention, encryption-at-rest responsibility, access controls, point-in-time recovery steps, and a restore drill.

## Reviews, reports, and automation

Create the following version-controlled artifacts:

- `docs/permissions.md`: role/action matrix and 401/403/404 semantics.
- `docs/testing.md`: unit, real-database integration, and Playwright critical-flow strategy; only external providers are mocked.
- `docs/security/threat-model.md`: assets, trust boundaries, entry points, OWASP threats, likelihood/impact, existing and missing mitigations.
- `docs/reviews/performance.md`: query inventory with file, line, issue, severity, and remediation. Only evidence-backed high-severity issues are fixed.
- `docs/reviews/test-quality.md`: prioritized weak-test, mock-only, skipped/flaky, and coverage-gap report.
- `docs/reviews/security.md`: independent release review. Findings are reported before remediation unless a separately approved implementation task covers them.

Dependency checks run in CI for Python and npm dependencies. Dependabot configuration opens update PRs. CI runs backend tests, frontend lint/build, dependency audits, and Playwright only when its browser/runtime dependencies are available.

## Verification

Every schema modification has an Alembic migration. Integration tests are generated from the permissions matrix and cover unauthenticated (401), disallowed same-organization (403), and cross-organization resource access (404). Team tests cover expiration, token/email binding, last-owner protections, transfer, immediate session revocation, and Chroma isolation. The complete backend suite, frontend lint/build, and a startup health check must pass after each implementation slice.
