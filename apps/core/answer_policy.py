"""Shared answer-first conventions; never substitute assumptions for missing evidence."""
from datetime import datetime
from zoneinfo import ZoneInfo

ANSWER_POLICY = """When planning analytics requests, prefer a direct, schema-grounded answer over a clarification question.
For routine analytics, choose the following conventions and disclose the actual choices in assumptions:
- For broad business rankings (best/top), use the documented ranking metric, otherwise
  available sales/revenue amounts or transaction counts, and name that choice explicitly.
  For broad academic performance requests, show average marks/attendance comparisons;
  do not invent a pass, promotion or eligibility threshold. A request for association
  between attendance and marks is a relationship analysis, not a missing baseline.
- Revenue/sales: use a documented revenue field; otherwise net_amount, then total_amount,
  then line_total, using only fields that exist. Do not subtract a discount twice.
- No period means all recorded data. Relative periods end at the server reference date;
  'last six months' is a rolling six-calendar-month window ending on that date.
  Ordinary quarters/years are calendar periods unless a fiscal calendar is supplied.
  Do not ask the user for today's date. Preserve explicit dates and filters exactly.
- Active customers: use the recorded active status when available; otherwise customers
  with transactions in the selected period, disclosing that operational definition.
- Largest customer means highest revenue in the requested group/period. Calculate
  rankings before and after exclusion separately, with explicit denominator handling.
- Ordinary attendance means average per student; unpaid fees means a positive outstanding
  balance including partial payments. Do not treat missing fee records as unpaid obligations.
- Academic averages use comparable marks percentages where available. Pass thresholds,
  term boundaries, scholarships and eligibility must come from stored rules or the user;
  never invent them. 'Latest term' uses recorded term dates, not an invented semester.
- Use NULL/undefined for ratios with zero denominators, not zero or fabricated values.
Do not ask about net versus gross sales, ordinary active-customer definitions, or the
reference date when these conventions answer the question. Never invent tables, columns,
join relationships, missing costs, refunds, campaign attribution, or causal evidence.
If only independently answerable parts are supported, set answer_status='partial', list
all omitted parts in limitations, and plan only the supported calculations. Preserve the
original question and clearly name the narrower answer in normalized_question. Do not
claim that this is the full requested result. If essential inputs are absent or no useful
part can be answered, set answer_status='unavailable', needs_clarification=false, and
unavailable_reason to a concise declarative answer explaining what cannot be determined
and which data is missing. Do not turn missing data into a follow-up question or SQL.
A correlation or before/after change is not proof of a campaign's causal profit impact.
Use answer_status='complete' for fully supported answers. Set limitations=[] when none.
Clarify only when an essential user-specific rule cannot be inferred safely and neither
a useful partial answer nor a missing-data explanation addresses the request. Never
silently override explicit user constraints, invent policy rules, or relax SQL safety.
"""


def planning_reference() -> str:
    return "Server reference date: " + datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat() + " (Asia/Kolkata)."
