# History state and deletion durability (audit F12/F11)

## Supported operating boundary

Run **one API process/worker**. Sync routes still execute on multiple threads;
all state mutation commands, snapshot capture and local memory writes/cleanup
share one reentrant owner lock. This is not a distributed lock, multi-worker
cache, HA design or PostgreSQL/pgvector migration. Provider calls, upload parsing
and read-only query execution run outside this lock. Bounded local Chroma work
and SQL state commits run inside it and can still wait on local disk I/O.

The existing relational application database is authoritative for API workspace
metadata, guardrails and history. Commands stage changes while holding the owner
lock, commit SQL, then expose the new cache state to other readers. SQL failure
restores the old cache; it does not acknowledge successful persistence. A JSON
checkpoint failure after SQL commit is logged, not reported as an undone commit.
History and workspace-list readers receive defensive snapshots.

JSON uses unique mode-0600 temporary files in the same directory, flush/fsync,
atomic replacement, directory fsync on POSIX and cleanup on failure. This covers
serialization and snapshot ownership, not only rename. It is a derived checkpoint,
not an independent transaction authority. Runtime server connection arguments
remain in memory only and are not written to SQL or JSON.

## Startup and legacy import

Migration `20261107_0017` adds the authority marker, memory generations and deletion
intents. Existing tenant state is marked authoritative even when all workspaces
have already been deleted. Startup never writes loaded JSON over SQL and never
merges stale JSON workspace fields over authoritative ownership.

The legacy importer is attempted once only for a never-authoritative database
with no tenant or workspace state, then its marker is committed with import.
Existing tenant-aware installations do **not** automatically import missing JSON
workspaces: missing may mean deliberately deleted. If an installation genuinely
has legacy-only data, review/recover it offline with the existing explicit
`import_legacy_local_state` helper and a backup; do not remove the authority marker
or enable blind automatic replay. This conservative rule can require manual
recovery of ambiguous old JSON instead of silently resurrecting deleted data.

Startup preserves only matching-owner runtime server connection arguments;
credentials still require reconnection after process restart, as before.

## Logical deletion versus physical cleanup

History deletion commits SQL history removal and a scoped durable deletion intent
in **one transaction**. Clear advances the tenant/workspace memory generation.
Individual deletion retains an exact-ID/generation tombstone. Workspace removal
also advances generation; suppression rows deliberately survive workspace removal.

Each approved history append captures its generation atomically. A delayed vector
upsert cannot fetch a fresh generation and pretend an old record is new. API/RAG
memory access goes through the guarded repository: it checks SQL ownership,
history membership, generation and individual tombstones. Policy lookup failures
fail closed for memory; RAG can continue without historical context. This does
not retract responses/prompts already delivered or cancel an in-flight model call.
Existing browser history/continuation caches (audit F06/F07) are not repaired here.

Physical cleanup is derived work. Bulk cleanup selects only non-current epochs,
including missing legacy generation metadata (zero). Later bulk clears may make
additional epochs eligible, but current-generation records are never selected.
Individual cleanup checks the exact scoped ID and captured generation. Selection
and local upserts use the same owner; deletion also retains the tenant/workspace
predicate. Reused IDs in a newer generation/other scope are preserved. API record
IDs are generated uniquely; individual tombstones prohibit reusing a deleted ID
within the same generation. Completed tombstones are retained to reject late saves.

The API returns **204** when history deletion and its cleanup have completed, or
**202** with `{"status":"deleted","cleanup_pending":true}` when logical deletion
is committed but physical cleanup is delayed. A relational failure is not a
successful deletion. Repeating individual deletion is a scoped idempotent no-op;
each explicit bulk-clear request clears the state present at its own serialized
commit point. A retry of physical intent never repeats an unqualified workspace
clear or removes newly current records. Workspace DELETE acknowledges logical
workspace removal; its vector cleanup is asynchronous.

## Recovery and operations

The same API process retries on startup and every 30 seconds: at most 10 due intents,
at most 200 vector candidates per intent, with durable exponential backoff
(2 seconds up to 256 seconds). A batch of exactly 200 remains pending until the
next batch confirms completion. There are no offset cursors over a changing
collection. Cleanup failure or retry-bookkeeping failure leaves suppression intact.
No separate cron/cleanup process should write to Chroma alongside this API owner.
Shutting down waits for the current bounded batch; local I/O has no hard latency SLA.

Back up the relational database **including markers, generations and all tombstones**,
the managed source files and Chroma coherently. Never restore stale JSON over SQL.
Retain completed suppression rows; automatic pruning is intentionally not implemented.
If restoring an older SQL backup or rolling code/schema back, stop the API and
review deletion privacy first: old SQL backups intentionally contain older state.
Purge/rebuild derived Chroma from authoritative approved history if its timeline is
uncertain. The additive migration has a schema downgrade, but removing its policy
and serving old code against old vectors does not preserve deletion guarantees.
No automatic downgrade, consolidation, deployment or backup job is performed here.

Memory recall may return fewer candidates while suppressed vectors await cleanup;
this favors avoiding deleted context over recovering every possible neighbor.

## Verification

`backend/tests/test_state_durability.py` uses file-backed SQLite and, when
`TEST_PERSISTENCE_POSTGRES_URL` is supplied, unique schemas in a dedicated disposable
PostgreSQL database. Never point this variable at production. CI supplies a fresh
PostgreSQL17 service. Tests perform real SQL/Chroma writes with synthetic data;
commit/storage failure injection is not a production fault simulation.

Coverage includes threaded workspace/history/settings/save/delete transitions,
concurrent actual CSV uploads, real concurrent distinct query approvals, SQL commit
rollback after flushed writes, stale JSON restart, JSON failure after SQL commit,
Chroma outage/reopen/retry, delayed indexing, ID reuse/new generations, scope
isolation, policy lookup failure, bounded batches/backoff and migration round trips.
Existing approval tests use local synthetic model/verifier doubles, not provider
calls. These tests do not prove Oracle ARM compatibility, browser cache correctness,
production connectivity, load capacity, HA or crash/power-loss behavior on real disks.
