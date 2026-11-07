# Password-reset and email-change code claims (audit F13)

Both routes claim a code with one conditional database UPDATE. The row must
still have the looked-up code hash and user, be unused and unexpired, and have
fewer than five incorrect attempts. Exactly one affected row authorizes the
account change. Another request cannot reuse the same code.

A successful claim is not committed separately. The account update, existing
session/login-challenge revocation, and (for email changes) replacement session
commit together. Any failure before commit rolls all of these back. The
old-address email notice is best-effort after commit, as before. No new email
provider or production database is needed to run the tests.

Wrong attempts use a database-side increment under the same eligibility
conditions. They commit even though the request returns the existing generic
401 response. The fifth incorrect attempt consumes the code; expired, used,
or exhausted codes do not keep incrementing. Hashing, expiry, rate limits,
CSRF checks, and generic invalid-code responses are unchanged.

## SQLite transaction boundary

The helper is called only after read-only lookups. It captures the code ID,
user ID, and hash, then rolls back that read-only transaction before its
conditional write. This avoids a stale read-to-write upgrade with SQLite's
explicit BEGIN or WAL modes; the conditional UPDATE, not the old snapshot,
decides eligibility. Callers reload the user before making any changes. Do not
call this helper after pending writes: its rollback would discard them.

## Regression tests

Run `python -m pytest -q backend/tests/test_sensitive_code_atomicity.py`.
The tests use independent sessions and physical connections, real concurrent
HTTP requests synchronized after code lookup, and real database writes.
They verify one winning account UPDATE, no lost incorrect-attempt increments,
last-attempt races, expiry/consumption/cap/hash rechecks, and rollback after
flushed writes or immediately before commit (including retry with the same
code). Email delivery is captured locally; no real messages are sent.

Four file-backed SQLite configurations cover legacy and explicit BEGIN, each
with rollback-journal and WAL modes. For PostgreSQL, set
`TEST_AUTH_POSTGRES_URL` to a **dedicated disposable test database**, never an
application or production database. Tests create and drop unique `otp_test_*`
schemas and require permission to do so. Without this variable the PostgreSQL
cases explicitly skip; CI supplies a disposable PostgreSQL 17 service.

These are auth-database tests, not workspace database connector tests. The
supported auth databases are SQLite and PostgreSQL; this change does not claim
MySQL auth support. Local synthetic tests do not prove production connectivity,
failover, browser behavior, or load capacity. No schema migration is required.
