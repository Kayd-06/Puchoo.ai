# Offline backup and fresh-directory restore (SQLite authority)

This supported workflow captures the relational accounts/workspaces/history database,
its authority marker, memory generations and deletion intents/tombstones, every
referenced managed uploaded SQLite dataset, and the paired scoped Chroma directory.
It does **not** capture `.env`, runtime server connection credentials, unreferenced
uploads, legacy `state.json`, or a PostgreSQL server. Server workspaces require
manual reconnection after recovery. For a PostgreSQL authority use a separately
validated coordinated database/Chroma recovery procedure; these commands reject
non-SQLite input rather than claim a complete server backup.

## Create

1. Stop **all** API, indexing, repair and maintenance writer processes and wait for
   process exit. This is an OFFLINE workflow, not an online multi-store transaction.
   The API holds a shared maintenance lease for the SQLite database during its
   lifespan; the backup needs an exclusive lease and fails if an API is active.
   This presence lease does not serialize queries or hold the application state
   mutation lock across provider calls. Separate/uncooperative writers still MUST
   be stopped. Do not equate an ASGI lifespan stopping with every SDK writer process
   having exited. Use the configured paired database/Chroma/uploads paths.
2. From the repository root, into a trusted private destination outside source trees:

```bash
python -m scripts.create_backup --database /srv/puchoo/auth.db \
  --chroma /srv/puchoo/chroma --uploads /srv/puchoo/uploads \
  --destination /secure/backups/2026-11-07T180000 --writers-stopped
```

Only referenced datasets within the managed upload directory are accepted. Missing
sources, unsafe paths, symlinks, SQLite corruption, a missing authority/deletion
schema, or Chroma changing while copied fail the job; do not report that snapshot
as successful. SQLite backup API includes committed WAL contents. Dataset files
are deduplicated. A versioned manifest includes mappings and SHA-256 file hashes;
the complete tree is published at once after private staging. An interrupted
publication may leave an empty reservation/staging directory, not a usable complete
backup. Only manifested snapshots qualify; delete/review incomplete artifacts
manually, never treat them as newer successful backups.

## Restore — explicit privacy/recovery gate

An older snapshot **cannot know deletions after it was taken**. Before EVERY
restore, review the newest retained deletion/privacy ledger against the selected
snapshot. If no trustworthy newer ledger is available, do not reconnect restored
memory/data to users until an offline privacy review and approved purge/rebuild
has completed. This tool does NOT merge newer tombstones automatically or promise
retroactive erasure of historical backups. Retain required deletion evidence outside
ordinary snapshot rotation under the applicable privacy policy. The acknowledgement
below records this operator decision, not proof of reconciliation.

```bash
python -m scripts.restore_latest_backup --backup-dir /secure/backups \
  --destination /srv/recovery/reviewed-2026-11-07 --acknowledge-privacy-review
```

The newest named manifested snapshot must validate; corruption never silently
falls back to an older backup. Legacy two-folder backups are rejected for manual
review because dataset files and suppression state were not guaranteed complete.
The old `--target-database`/`--target-chroma-dir` interface is intentionally removed.

The destination MUST NOT exist. Restore validates paths/hashes/schema/integrity,
stages all stores privately, relocates dataset references to `destination/datasets`,
and publishes one fresh directory. It never overwrites running or arbitrary
existing data. Failed staging cleans only its own temporary directory. Do not
start the application against the destination until the command succeeds and
privacy review is complete. Configure `DATABASE_URL` to `destination/auth.db`,
`CHROMA_PATH` to `destination/chroma` and `PUCHOO_UPLOAD_DIRECTORY` to
`destination/datasets`; verify startup, account login, workspace scope, known query
results and deletion suppression before any traffic. Keep one API process/worker.

Existing suppression tables/authority marker prevent a deleted vector copied in
the same snapshot from being recalled and prevent stale JSON imports. Local Linux
cold-process roundtrips are regression-tested; Oracle ARM, Windows locking,
production-sized storage, power-loss and actual deployment restore drills remain
release gates. Hashes detect accidental corruption, NOT malicious backup forgery:
use trusted operators, encrypted storage and access controls. Files are private
(0700 directories/0600 files); backups contain sensitive account hashes/data.
Set retention and quota from measured deployment capacity; keep snapshots outside
the web root/repository. Never auto-delete existing production data during recovery.

Maintenance `.maintenance.lock` sidecars persist by design and are ignored by Git.
Never unlink one while an API or backup may still hold it: that can create two
independent lock inodes and bypass mutual exclusion. Stop processes first.
