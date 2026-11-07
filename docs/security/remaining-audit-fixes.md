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
