# Notification stream authentication (F16)

Opening SSE still uses normal authentication/rate limiting and the existing
per-user open-stream cap. Each poll (every three seconds), and each event in a
batch, rechecks the original signed cookie against the current server-side
session, expiry/revocation/token binding, user, canonical tenant/role and durable
membership. Changed membership/role/tenant closes this connection; the client
must reconnect under its current identity. No session renewal or HTTP quota is
performed by the poll checks. Database failure closes fail-closed.

Short database sessions close before yielding, so a slow consumer does not retain
an authorization snapshot or transaction. Revocation normally takes effect by
the next poll (three seconds plus database/scheduler/network latency), or before
the next event. An event already authorized/in flight cannot be recalled, and
this is not a hard wall-clock SLA during database/network stalls.

Normal near-expiry authentication renewal cookies are copied to the streaming
response. An old stream token closes after expiry/rotation grace; EventSource
can reconnect using the renewed cookie. Server-side slots are released on close,
cancellation, disconnect and never-started responses. Browser cookie/reconnect
behavior and deployment proxy timeouts remain real-browser/deployment gates.

Synthetic SQLite tests mutate real sessions/membership between polls/events,
advance the JWT library's clock with a genuinely signed token, inject database
failure, and exercise actual renewal header propagation. These are not browser
or production-load measurements.
