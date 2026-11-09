# Remaining audit fixes: SQL meaning preservation

This branch implements the remaining scoped audit controls for review, not a
production-readiness certificate. Automatic guarded read-only execution remains the product behavior.
The `/approve` protocol is an execution claim, not a mandatory user preview step.

## F20: bounded automatic runtime repair

Replacement SQL must pass the original question/plan validators and preserve the
SQL AST: population predicates (including date/class), metric, joins, grouping,
ordering and limits. Unsupported rewrites fail with a clear message; they do not
create a replacement pending query or execute it.

The only structural exception currently implemented is insertion of an exactly
representable floating-point cast on a numeric **literal inside ABS**, for example
SQLite's signed-integer-minimum overflow. Column casts are not allowed: widening a
column could round other rows. Existing casts cannot be removed or narrowed. This
is deliberately conservative, not a general equivalence prover. Broader repairs
need independent, proven rules. Successful permitted repair still runs through the
normal automatic frontend flow once, using a fresh once-only execution claim.

## F24: whole-intent deterministic templates

Templates and canonicalization consume a complete recognized sentence, not loose
keywords. An extra year, class, category, region, customer, top-N or custom trend
rule sends the original question intact to the normal planner. Unknown wording is
not rejected merely because a template cannot support it. The fixed complex demo
rules are recognized narrowly; the model remains responsible for other questions.
This does not prove every possible model-generated query answers its question.

## F17: complete translation input

The application translation bound is 2,000 characters. Longer translated questions
return an explicit 422 before constructing a provider client; English questions
retain their existing 4,000-character request bound. The adapter also rejects long
text instead of slicing it, so trailing constraints are never silently discarded.
Display translation continues using its English fallback when a bound is exceeded.

## Validation scope

Regression fixtures use fake SQL/translation providers, actual local SQLite query
execution, and structural contracts parsed as SQLite/PostgreSQL/MySQL SQL. They are
not external provider, managed database, mobile/browser or Oracle ARM validation.
See the workstream manifest outside the repository for current executed counts and
remaining audit IDs. Other audit fixes are not claimed complete by this document.

Repair widening is restricted to a final scalar projection without downstream alias references; exact literal representation alone does not prove arithmetic or aggregate type-promotion equivalence. Workspace `postgresql` aliases use the same SQLGlot dialect normalization as the guardrails.

## F25: explicit clarification choices

The browser submits the original scoped question and a bounded list of reason/choice answers, not an appended free-form `Clarification:` suffix. The server replays only choices it actually offers for that question, after translating the original question. Calendar selection changes only the calendar, and classification choices retain all original filters. Multi-step choices retain earlier definitions. Stale or fabricated choices fail before SQL planning.

A field choice is not a policy or threshold: educational metric, eligibility, missing-input and scoring-rule choices advance to a distinct detail prompt with no executable proposal. The user must edit/rephrase the question with actual rules, preserving their filters. No scoring or eligibility policy is invented. Available-fields selection displays only the current workspace schema. Explicit marks/attendance comparisons can then be processed without repeating the metric question.

## F19/F21/F22: resilient, durable answer presentation

Translation client construction as well as translation calls can fall back to the exact English rows/labels with an explicit unavailable flag. Verifier adapter/factory/serialization exceptions return a fixed advisory-unavailable explanation, never raw SDK exception bodies, endpoints or credential-like text; a failed independent check does not erase a valid database answer or allow execution replay.

Localized headline, labels, column labels, highlights and display rows are persisted alongside immutable raw numeric facts. Presentation is computed outside the state lock, then conditionally patched only into the same surviving tenant/workspace/history generation and approval identity. A deletion during translation prevents the patch; it does not recreate a record. A reused ID in a later generation is untouched. SQL commits before cache/checkpoint publication, and a failed presentation commit retains the original English answer. Incremental history synchronization now writes changed existing payloads instead of silently ignoring them. History exports use these saved fields, with old-record English fallback. This remains a single-API-process architecture, not a multiworker claim.

## F15/F14: recoverability and preallocation limits

Offline snapshot/restore now captures the SQL authority/deletion policy, managed uploaded databases and scoped Chroma together; runtime-only credentials and legacy JSON are excluded. Restore is fresh-directory only, verifies hashes/path/schema integrity, relocates dataset paths and requires explicit newer-deletion/privacy review. Active SQLite API lifespans prevent backup via a maintenance presence lease. This is NOT an online multi-store snapshot or automatic reconciliation of deletions newer than a backup. See the [operational runbook](../runbooks/backups.md).

Import now validates ZIP metadata and streams CSV/XML shape/text/complexity preflight before dataframe construction, including cumulative sheets/files, sparse/repeated coordinates and shared strings. Limits can lower but not exceed hard ceilings. Legacy XLS is explicitly unsupported; convert first. Reproducible selected boundary-resource probes are helper-only Linux observations, not universal peak-memory or Oracle/ARM/load guarantees. See the [bounded parser policy](upload-parser-bounds.md).


## Review and release gates (not executed acceptance)

All 27 audit IDs are accounted for: seven source fixes were merged in PR60–63,
F04/F05 were already closed, and this branch implements controls for the remaining
18 IDs. Implementation is not deployment or closure of unexecuted acceptance.

- F03 corrects product copy; Enter still runs guarded read-only SQL automatically,
  with conservative safe automatic repair and optional SQL inspection.
- F08/F18 add scoped microphone cleanup and IME submission handling. Synthetic
  DOM/media events do not prove native permission, microphone or IME behavior.
- F09 bounds each PDF capture before allocation; total browser/PDF memory and
  multilingual visual readability still require real-browser review. See
  [PDF bounds](pdf-export-bounds.md).
- F10: AskData really animates particles. Adaptive limits, reduced-motion and
  visibility controls are implemented; no mobile throughput, battery or OOM
  improvement has been measured. See [resource policy](query-universe-resources.md).
- F16 revalidates live SSE sessions and membership before delivery; synthetic
  database tests are not a deployed proxy/disconnect/load exercise.
- F23 fixes the PowerShell migration working directory and exit propagation;
  actual Windows execution remains untested.
- F26/F27 add local contrast rules and a canonical mobile workspace selector.
  Browser attempts failed with connection refused before loading any page,
  despite successful box-side HTTP checks. No visual/theme/viewport/contrast,
  native IME/microphone or PDF browser acceptance was performed. Box health
  checks passed; a cause for the browser refusal was not established.

Release review must retain the offline **SQLite-only** backup scope, fresh-target
restore, explicit newer-deletion/privacy acknowledgement, and single-API-process
limit. Older snapshots cannot automatically know deletions made afterward.
Legacy XLS is unsupported: convert to CSV/XLSX. Partial translation is rejected,
not silently truncated; conservative SQL repair can require rephrasing.

Dependency audits retain existing CI exceptions: raw Python audit reports five
Chroma 1.5.9 records representing four unique advisory IDs (PYSEC-2026-311 appears
twice). No new waiver or dependency change is made here. An npm audit reporting
zero vulnerabilities does not make the Python dependencies vulnerability-free.
Review these existing exceptions before release.

No real-provider, production-load, actual Windows, Oracle/ARM, mobile-hardware,
power-loss or deployment validation is claimed. PostgreSQL/pgvector consolidation
remains deferred. Browser validation is a documented release gate, not a reason
to represent this review PR as deployment-ready.
