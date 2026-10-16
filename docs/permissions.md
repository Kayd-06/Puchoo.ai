# Current API permissions

| Surface | Authentication | Minimum role | Foreign tenant/resource result |
| --- | --- | --- | --- |
| `/api/health`, `/api/v1/auth/csrf`, signup/login/password recovery | Public | — | — |
| Session/account endpoints | Session cookie | Account owner | 401 without a valid session |
| Workspace list and history reads | Session cookie | viewer | 404 for another tenant's workspace |
| Workspace schema/table reads | Session cookie | editor | 404 for another tenant's workspace; 403 for viewer |
| Query generation/execution and language input | Session cookie + CSRF | editor | 404 for another tenant's workspace; 403 for viewer |
| Uploads, server database connections, guardrail changes, workspace delete, invite-code generation | Session cookie + CSRF | admin or owner | 404 for another tenant's workspace; 403 for editor/viewer |
| Invite-code member role change/removal | Session cookie + CSRF | admin or owner | 404 for a non-member; 403 for viewer/editor |
| Notifications | Session cookie + CSRF for writes | notification owner | 404 for another user's notification |

JWTs are HttpOnly cookies. State-changing routes require the double-submit CSRF cookie/header pair. UI visibility is never an authorization control; the route must enforce this matrix.

## Role change: editors no longer manage data sources

Editors can still ask questions, review generated SQL, run approved queries and read history, but **uploads and data-source management are now owner/admin only** (`manage_data_sources` is `false` for editors in `backend/authorization.py`).

- API: `POST /api/workspaces/upload` and `/upload-multiple` return **403** for editors and viewers (`backend/tests/test_workspace_upload.py::test_editor_cannot_upload_data_sources`).
- UI: the Sidebar hides "Data sources" and `ConnectData` shows a protected-state message with no file input for editors (`frontend/src/pages/__tests__/role-surfaces.test.jsx`).
- Existing editors who used to upload should ask a workspace owner or admin to upload, or be promoted to admin.
