# Testing strategy

Puchoo.ai uses three proportional levels:

- **Unit tests:** business and safety logic in `apps/core` and scripts, including SQL guardrails, database connection validation, Chroma scope helpers, and backup restore safety.
- **Integration tests:** FastAPI routes with a temporary SQLite database. These exercise real authentication, CSRF, roles, session revocation, and tenant boundaries. SMTP and external model/voice providers are mocked at their network boundary only.
- **Browser build verification:** Vite production build and ESLint run in CI. Playwright is intentionally not added yet because the app has no browser-test fixture/runtime; add it only when a user-critical browser regression cannot be covered by API integration tests.

Every authorization change needs a 401, same-tenant 403, and foreign-tenant 404 case where applicable. Every bug fix starts with a test that fails for the original behavior. Do not replace database or authorization checks with mocks.
