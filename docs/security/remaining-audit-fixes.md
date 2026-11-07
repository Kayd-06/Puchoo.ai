# Remaining audit fixes: SQL meaning preservation

This branch is an incomplete release-fix workstream, not a production-readiness
certificate. Automatic guarded read-only execution remains the product behavior.
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
