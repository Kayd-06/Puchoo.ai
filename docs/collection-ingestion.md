# Collection ingestion architecture

## Product model

A user creates a **collection** before uploading files. A collection is one
organization's coherent data context and has exactly one domain:

- `business` for inventory, sales, suppliers, finance, HR, and operations
- `education` for a school, institute, or college

One chat is attached to one collection. The query service receives the
collection ID from the authenticated session and never accepts a client-chosen
database, table, or domain outside that collection. Therefore a Business chat
cannot query Education data, even for the same user.

## Production storage boundary

The Streamlit importer is appropriate for a local pilot and modest collections.
It intentionally creates one local SQLite database per collection. It must not
be used as the production path for tens of thousands of files.

For production, use these services:

| Service | Responsibility |
| --- | --- |
| API and identity service | Authenticates the user and authorizes a tenant, domain, and collection. |
| Metadata database | Stores collections, source files, versions, ingestion jobs, schema summaries, and access policy. |
| Object storage | Stores original uploaded files under a tenant/domain/collection/version prefix. |
| Queue and worker pool | Parses files asynchronously, deduplicates by checksum, and writes normalized columnar data. |
| Lakehouse/query engine | Reads normalized Parquet or Iceberg data and executes the read-only analytical query. |
| Schema retrieval service | Selects only the relevant table and column summaries for the question before SQL generation. |

Use a storage prefix and catalog partition such as:

```text
tenant/{tenant_id}/domain/{business|education}/collection/{collection_id}/version/{version_id}/
```

The query engine must enforce the same tenant, domain, and collection filters
server-side. UI filters and prompt instructions are helpful, but are not a
security boundary.

## Upload and ingestion flow

1. The client creates a collection with its domain.
2. The API returns short-lived multipart upload URLs and an ingestion job ID.
3. The client uploads files directly to object storage and submits a manifest.
4. Workers validate file type and size, scan for malware, calculate a checksum,
   and parse files independently.
5. Workers write partitioned columnar tables and a file/table/schema catalog.
6. The job records per-file status, errors, row counts, and the committed
   collection version.
7. Chat queries only the latest successful version, or an explicitly selected
   prior version.

This keeps a 100,000-file upload out of the web request and avoids loading all
files into application memory. Jobs are idempotent by collection, file checksum,
and source version, so a failed batch can be retried without duplicating data.

## Chat across many files

Do not place every schema in an LLM prompt. At scale, index concise table and
column descriptions plus file provenance. For each question, retrieve a small
set of relevant datasets, generate read-only SQL over only those datasets,
validate it against the collection-scoped catalog, and execute it with row,
time, and byte-scan limits. Show the source files and tables used with the
answer.
