# Bounded tabular import policy (F14)

CSV/XLSX import runs streaming preflight **before** pandas/openpyxl creates frames.
Legacy XLS is rejected with conversion guidance: the binary parser's allocation
behavior is not covered by this policy. The file picker and current documentation
now advertise CSV/XLSX, not XLS. Save a legacy file as XLSX or UTF-8 CSV first.

## Hard ceilings

Configuration may lower, but cannot raise these conservative preallocation ceilings (not RSS guarantees):

- 25 MiB input for one file **or an entire multi-file collection**; the route reads
  each next part using only the remaining budget. Multipart spooling/proxy limits
  still need deployment configuration; this is not a whole-HTTP-body disk guarantee.
- 250,000 data cells cumulatively across sheets/files; 500 columns, 1,000,000 rows,
  50 sheets. Dense extents, declared dimensions, physical repeated rows/cells and
  sparse coordinates are all counted before any sheet is materialized. Empty row
  spans cost at least one logical cell each. All ceilings apply simultaneously.
- XLSX ZIP: 32 MiB expanded, 8 MiB per internal part, ratio100 by default, 10,000
  entries, 4 MiB directory metadata, 1,024-byte part names. Raw directory metadata
  is checked before ZipFile allocates entry objects. ZIP64/multipart/unusual
  compression layouts, encrypted and duplicate parts are rejected.
- XML: 1,000,000 elements, depth64, 64 attributes per node, 64 KiB lexical token,
  10,000 style objects, 250,000 shared strings. Repeated/external worksheet targets
  and reused worksheet relationship IDs are rejected so multiple sheet aliases
  cannot multiply a once-accounted part. DTD/entities are forbidden. XML is
  preflighted by content even under a nonstandard part name: relationship targets
  cannot evade shape/complexity checks by using a `.bin` name. Ordinary non-XML
  images/print settings are ignored, still subject to byte ceilings.
- 16 MiB text per file and 32 KiB per field. CSV preflight counts delimiters without
  building a row list, including multiline headers, escaped quotes and CRLF. Invalid
  quoting or extra data fields are rejected rather than shifting columns silently.

Remaining collection cell capacity is passed to the next file's preflight; it is
not checked only after parsing every sheet/file. Each workbook closes on success
or decoding failure. The old frame checks remain as defense in depth, not the
primary resource boundary. Malformed driver metadata is a safe400 import error.
Partial derived SQLite workspaces are removed on failed import.

Some unusual/over-budget files previously attempted by pandas are intentionally
rejected; lower the data volume or export data-only CSV/XLSX. Limits constrain
input/work and logical allocations, not an OS-enforced absolute RSS limit. Account
for concurrent requests, SQL/Chroma baseline, multipart spool disk, native allocator
behavior and dependency versions in deployment capacity planning. Never raise the
hard ceilings without new adversarial/resource tests.

## Reproduce evidence

From repository root: `python -m scripts.probe_upload_budgets`.

The probe generates only synthetic fixtures; each of five alternating trials per
workload is a fresh child process. It checks accepted shapes/checksums/field lengths and
expected rejection reasons. Timings include input read and parser helper work,
NOT HTTP latency, SQLite creation, provider calls or concurrent production load.
Kernel `/proc/self/status` VmHWM supplies per-exec peak RSS; raw ru_maxrss is retained
only as a diagnostic because it can inherit pre-exec parent high water. A separate
profile identifies the max-text CSV byte-preflight loop as CPU-bound on one core;
profiling results are excluded from the reported trial timings.

Initial local engineering acceptance is under256MiB/5seconds for these selected
boundary probes, otherwise investigate/lower caps before publication. This is a
local review criterion, NOT an enforced runtime memory/time SLA or an exhaustive
worst-case proof. Current Linux x86_64, Python3.12/pandas2.3.3/openpyxl3.1.5 observations
and every raw trial are kept in the audit checkpoint's `parser-resource-probes.json`.
No before/after speedup claim is made. Oracle/ARM, Windows, production data,
concurrency/load and full upload-to-query capacity validation remain release gates.
