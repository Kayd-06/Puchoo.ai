# Backups and restore drill

## Scope

This runbook covers the current local persistence used by Puchoo.ai:

- the SQLite account database (`backend/puchoo_auth.db` by default);
- the Chroma approved-conversation store (`CHROMA_PATH`, default `.pucho/chroma`).

It does not cover a future R2/S3 integration or manage a production PostgreSQL service.

## Backup policy

- Run one application-consistent snapshot daily.
- Retain 35 daily snapshots; keep backups encrypted at rest using the deployment provider’s managed encryption.
- Restrict read/write access to the backup operator role. Never store snapshots in the web root or source repository.
- A snapshot directory must contain `auth.db` and `chroma/`, and be named in sortable UTC format such as `2026-10-07T00-00-00Z`.

Create a local snapshot only while the application is stopped, or use the SQLite backup API in the deployment job so the database copy is consistent. Copy the Chroma directory from the same maintenance window.

## Restore drill

Never restore over a running or production database. Choose new, empty destinations outside the application’s normal state paths:

```bash
python scripts/restore_latest_backup.py \
  --backup-dir /secure/puchoo-backups \
  --target-database /tmp/puchoo-restore/auth-restore.db \
  --target-chroma-dir /tmp/puchoo-restore/chroma
```

The command refuses existing paths and production-like target names. It selects the newest complete snapshot, copies the SQLite and Chroma artifacts separately, and runs SQLite `PRAGMA integrity_check`.

After a restore drill, start an isolated application process with the restored SQLite path and `CHROMA_PATH`; verify health, a test account lookup, and a tenant-scoped memory query. Record the date, snapshot identifier, operator, duration, result, and any corrective action in the operational log. Remove the temporary restore directory after the drill.

## Point-in-time recovery

If production later uses PostgreSQL, configure provider-managed point-in-time recovery and document the provider, retention period, recovery owner, and a separately tested restore procedure here. Do not point this SQLite restore command at PostgreSQL.
