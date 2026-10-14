# Role Sharing and UI Hardening Design

## Objective

Make business and institution collaboration reliable across refreshes and deployments, enforce one consistent role model in the API and UI, and clean up the authenticated product interface without changing the query engine's core behavior.

Success means:

- a user who joins with an admin, editor, or viewer code receives the correct persistent tenant membership;
- all members see only workspaces belonging to that business or institution;
- owners and admins can add data and manage access;
- editors can query existing shared data but cannot add, connect, delete, or administer it;
- viewers can inspect shared history and results but cannot query or modify workspace data;
- every user can see their effective role and manage their own profile image and verified email;
- OTP screens are clear, responsive, accessible, and resistant to duplicate actions;
- decorative glowing tags and ornamental security effects are removed while semantic status badges remain;
- CI proves the role matrix, tenant isolation, migrations, frontend build, and dependency health.

## Confirmed Role Matrix

| Capability | Owner | Admin | Editor | Viewer |
| --- | --- | --- | --- | --- |
| View tenant workspaces | Yes | Yes | Yes | Yes |
| View shared history/results | Yes | Yes | Yes | Yes |
| Inspect schema and query existing data | Yes | Yes | Yes | No |
| Upload files | Yes | Yes | No | No |
| Connect database servers | Yes | Yes | No | No |
| Delete workspaces/history | Yes | Yes | No | No |
| Change guardrails | Yes | Yes | No | No |
| Generate/rotate invite codes | Yes | Yes | No | No |
| Manage member roles/removal | Yes | Yes | No | No |
| View own account settings and role | Yes | Yes | Yes | Yes |
| Manage own profile image/verified email | Yes | Yes | Yes | Yes |

The backend enforces this matrix. UI visibility is an additional usability layer, never the security boundary.

## Architecture

### Central authorization policy

Replace scattered role checks with named capabilities derived from the authenticated user's effective tenant membership. The policy exposes predicates and FastAPI dependencies for:

- `view_workspace`
- `query_workspace`
- `manage_data_sources`
- `administer_workspace`
- `manage_account`

The owner is represented as an effective role, not inferred differently by individual routes. Every workspace-scoped route resolves the workspace first through the user's tenant boundary, then applies the required capability. A resource owned by another tenant returns 404; an in-tenant resource forbidden to the user's role returns 403.

### Persistent tenant and workspace metadata

The relational database is the source of truth for users, tenant membership, workspace metadata, ownership, role assignments, guardrails, and history indexes. Existing `workspace_owner_id` fields remain readable during migration, but application code resolves membership through one canonical tenant identifier.

Workspace source payloads remain in controlled application storage. Database rows store stable metadata and a source reference; they do not expose database credentials or arbitrary filesystem paths to clients. Existing query and schema services receive a resolved internal workspace record, preserving the current execution engine.

The legacy `.pucho/state.json` loader is migration input and a development fallback only. New or updated shared records are database-backed. Migration is idempotent and does not duplicate workspaces when startup runs more than once.

### Invite redemption

Invite codes remain hashed, role-specific, expiring, revocable, and independently rotatable. A valid code identifies the canonical tenant and desired role. Signup creates the user and membership in one transaction. OTP verification creates the session but does not change role or tenant assignment.

Admin-created codes remain attached to the original tenant. Removing a member revokes their active sessions. Role changes take effect on the next authorized request because capabilities are derived from persisted membership rather than cached client state.

### Shared data visibility

Workspace listing queries by canonical tenant ID. All members of the same business or institution receive the same permitted workspace metadata. The selected workspace remains browser-local, but the available list is server-authoritative. A stale selection is discarded if it is not returned by the current tenant-scoped list.

Server connection secrets remain server-only. If a source cannot be restored after deployment, the workspace is returned with an explicit unavailable state rather than silently disappearing or exposing credentials.

## API and Data Flow

1. Password authentication opens an OTP challenge.
2. Successful OTP verification returns the authenticated account with canonical tenant, workspace type, effective role, capabilities, and profile image.
3. The frontend loads tenant-scoped workspaces and selects the first valid record when its saved selection is stale.
4. Navigation and actions render from server-issued capabilities.
5. Each API route independently verifies the same capability before reading or mutating data.
6. Workspace history, schema, and query operations use the authenticated tenant plus workspace ID; they never accept ownership from the browser.

The account response includes a compact capability object so the frontend does not reproduce policy logic. The backend remains authoritative if the UI is modified or bypassed.

## Product UI

### Navigation and dashboards

- Owner/admin: Ask Data, Data Sources, History, Settings.
- Editor: Ask Data, History, Settings. Data Sources and all upload/connection controls are absent.
- Viewer: History and Settings. Query and data-source controls are absent.

Direct navigation to a forbidden page shows a clear role-aware access state and the API still returns 403 for prohibited operations.

### Settings

Every role receives an account settings page with:

- profile image upload and secure HTTPS-link options;
- name and verified email;
- tenant/workspace name and type;
- a flat semantic badge showing Owner, Admin, Editor, or Viewer;
- concise permissions copy explaining what the role can do.

Owner/admin additionally receive invite-code and member-management panels. Editor/viewer never receive administrative controls. Viewer settings no longer collapse into a generic blocked page.

### Profile images

Profile images persist against the user account and appear in Settings, the top bar, and account menu. Uploads accept PNG, JPEG, WebP, and GIF within the configured size limit. Link mode accepts HTTPS URLs only. Invalid formats, oversized files, broken previews, and failed saves produce inline errors. Remove and replace actions are available to every authenticated role.

### OTP screens

Login, signup verification, password reset, and email-change verification use a shared OTP component with:

- six numeric cells backed by one accessible input;
- paste support and automatic focus progression;
- visible expiry countdown;
- resend cooldown and attempt feedback;
- disabled duplicate submissions;
- preserved email context;
- clear expired, locked, invalid, network, and success states;
- mobile and keyboard accessibility.

### Visual cleanup

Use the approved direction: retain flat semantic badges for roles, verification, errors, warnings, and real system state. Remove:

- animated scanning beams and glowing border sweeps;
- pulsing ornamental dots and fake telemetry;
- decorative `Tenant isolated`, `HttpOnly session`, and `Guardrails active` tags;
- non-informational glow shadows and status pills;
- motion that does not communicate state.

Subtle elevation, focus rings, and restrained hover feedback remain. Reduced-motion behavior remains supported.

## Error Handling

- Invalid, expired, or revoked invite: generic invalid-code message without tenant disclosure.
- Role forbidden: 403 with a role-specific explanation.
- Foreign tenant resource: 404 without confirming existence.
- Removed member: active sessions revoked and subsequent requests return 401.
- Source unavailable: stable workspace card with unavailable status and owner/admin recovery action.
- OTP expired/locked: return to credential step with an actionable message.
- Profile upload/link failure: preserve current image and show inline error.
- Migration failure: abort startup rather than serving partially migrated authorization data.

## Migration Strategy

1. Add `tenants`, `tenant_memberships`, `workspace_records`, `workspace_guardrails`, and `workspace_history_records` tables. `workspace_records` contains the tenant ID, public metadata, source kind, opaque internal source reference, availability state, and timestamps; it never contains browser-visible credentials.
2. Backfill canonical memberships from `workspace_owner_id` and legacy institute fields.
3. Import eligible `.pucho/state.json` workspace metadata idempotently.
4. Run dual-read compatibility only for the migration window; all new writes go to the database.
5. Remove legacy authorization reads after verification proves equivalent tenant visibility.

Migrations support SQLite development and the configured production database. Downgrades preserve user accounts and avoid deleting uploaded source artifacts.

## Testing

### Backend

- invite redemption for admin/editor/viewer;
- admin-issued codes remain in the original tenant;
- same-tenant workspace visibility for all four roles;
- cross-tenant workspace, history, and query denial;
- owner/admin upload and connection success;
- editor/viewer upload and connection denial;
- editor query success and viewer query denial;
- member role changes take effect without recreating the account;
- member removal revokes sessions;
- refresh/restart persistence for memberships, workspace metadata, profile images, and history;
- invalid/expired/revoked invite behavior;
- schema migration and idempotent legacy import.

### Frontend

- role-aware navigation and forbidden-route states;
- effective role shown in Settings for all roles;
- admin panels absent for editor/viewer;
- data-source controls absent for editor/viewer;
- profile image upload/link/remove states;
- shared OTP input behavior and responsive layouts;
- no decorative security tags or glow animations in authenticated screens.

### End-to-end matrix

Create an owner and one member per role, join each with a real invite code, sign in through OTP, then verify visible workspaces and allowed/forbidden actions. Repeat after backend restart to prove persistence.

## CI and Delivery

The GitHub Actions pipeline runs:

1. database migration checks from a stale supported revision to head;
2. backend unit/integration tests, including the role matrix;
3. frontend lint and production build;
4. frontend component/end-to-end role tests;
5. Python and npm dependency audits using documented exceptions only;
6. Alembic's metadata-drift check against the test database.

Deployment must run migrations before accepting traffic. A failed migration or authorization test blocks delivery.

## Scope Boundaries

- No billing, organization hierarchy, or custom-role builder.
- No public profile images or public workspace sharing.
- No rewrite of SQL generation/execution beyond replacing workspace lookup with the canonical tenant-scoped repository.
- No storage of raw server credentials in client-visible metadata or the relational workspace table.
- No restoration of obsolete Streamlit UI files; stale tests are removed or replaced with tests for the active React application.
