# Current API permissions

| Surface | Authentication | Minimum role | Foreign tenant/resource result |
| --- | --- | --- | --- |
| `/api/health`, `/api/v1/auth/csrf`, signup/login/password recovery | Public | — | — |
| Session/account endpoints | Session cookie | Account owner | 401 without a valid session |
| Workspace list and history reads | Session cookie | viewer | 404 for another tenant's workspace |
| Workspace schema/table reads | Session cookie | editor | 404 for another tenant's workspace; 403 for viewer |
| Query generation/execution, uploads, guardrail changes | Session cookie + CSRF | editor | 404 for another tenant's workspace; 403 for viewer |
| Server database connections, workspace delete, invite-code generation | Session cookie + CSRF | admin or owner | 404 for another tenant's workspace; 403 for editor/viewer |
| Invite-code member role change/removal | Session cookie + CSRF | admin or owner | 404 for a non-member; 403 for viewer/editor |
| Notifications | Session cookie + CSRF for writes | notification owner | 404 for another user's notification |

JWTs are HttpOnly cookies. State-changing routes require the double-submit CSRF cookie/header pair. UI visibility is never an authorization control; the route must enforce this matrix.
