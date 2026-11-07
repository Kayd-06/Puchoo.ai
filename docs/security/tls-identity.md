# Verified TLS for email and workspace databases

Audit fixes: **F01 (SMTP)** and **F02 (workspace PostgreSQL/MySQL identity)**.
Automatic guarded read-only SQL execution and safe automatic repair are unchanged.

## SMTP

Both implicit TLS (`SMTP_USE_SSL`) and STARTTLS (`SMTP_USE_TLS`) use
`ssl.create_default_context()`: the certificate must have a trusted chain, valid
dates and a hostname matching `SMTP_SERVER`. STARTTLS is required when selected;
a missing capability or handshake failure never falls back to plaintext login.
The two modes cannot be enabled together. Production refuses delivery when both
are disabled, before opening a socket. An explicitly selected development-only
plaintext SMTP transport remains available for local development.

Trust comes from Python/OpenSSL's normal system trust configuration, including
`SSL_CERT_FILE`/`SSL_CERT_DIR` where supported. Install a private CA through the
server's controlled trust store if required; do not turn certificate checks off.

## Workspace database identity is not its network route

The connection form's original hostname is retained in the password-free URI.
The existing SSRF check still resolves it, rejects blocked/mixed addresses unless
explicitly allowlisted by the server operator, and chooses a checked numeric IP.
That IP is pinned for the lifetime of the workspace connection settings:

- **PostgreSQL/libpq:** `host` is the original URI hostname, `hostaddr` is the
  checked IP, and `sslmode=verify-full`. `hostaddr` controls network routing
  without a second DNS lookup; `host` controls certificate hostname validation
  and SNI. `DB_SSL_ROOT_CERT` selects a CA bundle; otherwise certifi is used.
- **MySQL/PyMySQL:** both `ssl_verify_cert` and `ssl_verify_identity` are true.
  `DB_SSL_CA` selects a CA bundle; otherwise certifi is used. A SQLAlchemy
  `do_connect` hook constructs a deferred PyMySQL connection and supplies a
  socket connected directly to the checked numeric IP via
  `Connection.connect(sock=...)`. The driver's `host` remains the original
  hostname for SNI and certificate checking. This runs on **every new pooled
  connection**, for schema inspection and query execution alike. No global
  DNS monkeypatch or disabled hostname checking is used in production code.

Read-only roles, SQL guardrails, local-infile denial, timeouts and credential
masking remain in place. Do not replace IP pinning with an ordinary hostname
connection, or verify only the IP when the certificate identifies the original
DNS name. If the user supplies an IP as the host, its certificate must identify
that IP. Operators must explicitly reconnect when DNS/endpoints change.

### Configuration compatibility

The default PostgreSQL mode is now `verify-full`. Legacy `DB_SSL_MODE=require`
and `verify-ca` values are accepted **but upgraded to verify-full**, never used
to weaken hostname checking; unsupported modes fail startup. Private deployments
must supply the correct CA bundle and a certificate matching the supplied host.
Older example configuration comments describing a verify-full restriction are
superseded by this policy; existing environment/secret files are not rewritten.

`DB_SSL_REQUIRED=false` is an explicit **development-only** opt-out, rejected in
production. For PostgreSQL it sets `sslmode=disable` explicitly rather than
inheriting libpq's ambient/prefer behavior; for MySQL it sets `ssl_disabled=True`.
The checked endpoint is still pinned. These settings apply to **workspace source
connections**; the operator-managed authentication `DATABASE_URL` is a separate
configuration boundary.

Reconnect existing server workspaces to build the new identity/endpoint settings.
Server passwords are still runtime-only; this change does not persist secrets or
add automatic recovery of source passwords after restart.

## Regression evidence and limits

Run `python -m pytest -q tests/unit/test_tls_transports.py` with OpenSSL installed
(the Ubuntu CI runner includes it). Fixtures generate disposable CA/server
certificates and use loopback-only minimal SMTP, PostgreSQL and MySQL protocol
peers. Real smtplib, psycopg/libpq and PyMySQL clients test:

- trusted CA plus matching original hostname succeeds;
- wrong-host, untrusted and expired certificates fail before application
  credentials/startup are sent;
- absent STARTTLS/MySQL SSL/PostgreSQL SSL support fails without plaintext auth;
- original-name SNI is retained, and database hostname resolution happens only
  once before pinning (including fresh pooled connections);
- both schema inspection and execution use the pinned MySQL transport;
- production plaintext SMTP/database opt-outs are refused.

These are real **local TLS/driver-contract** tests, not a real database-engine
query suite, external SMTP delivery test, managed-service compatibility proof,
Oracle ARM test or deployment certification. SQLAlchemy capability discovery is
suppressed in the minimal database peers because they do not implement SQL.
Keep normal query/guardrail/auth tests as well, and smoke-test actual controlled
service environments separately before release. No real provider credentials or
billable calls are needed for these regressions.

Driver contracts:
- [PyMySQL connection options and deferred connections](https://pymysql.readthedocs.io/en/latest/modules/connections.html)
- [SQLAlchemy do_connect hook](https://docs.sqlalchemy.org/en/20/core/events.html#sqlalchemy.events.DialectEvents.do_connect)
- [libpq host/hostaddr and SSL parameters](https://www.postgresql.org/docs/current/libpq-connect.html)
