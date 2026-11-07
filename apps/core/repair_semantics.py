"""Conservative structural contract for automatic runtime SQL repair.

A read-only repair is not safe if it changes the selected population or metric.
Only numeric widening inside ABS/SUM/AVG is automatically accepted for runtime
numeric overflow. Other rewrites need a new question/plan, not silent execution.
This is a bounded repair policy, not a general SQL equivalence prover.
"""
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


def repair_preserves_query(original: str, replacement: str, *, dialect: str = "sqlite") -> bool:
    def same(left, right):
        # Permit insertion, never removal/narrowing of an existing cast. Scope
        # predicates and all other expressions must remain structurally equal.
        if (isinstance(right, exp.Cast) and not isinstance(left, exp.Cast)
                and isinstance(right.parent, (exp.Abs, exp.Sum, exp.Avg))
                and getattr(right.args.get("to").this, "name", "") in {"FLOAT", "DOUBLE"}):
            return same(left, right.this)
        if type(left) is not type(right):
            return False
        if isinstance(left, exp.Expression):
            return left.args.keys() == right.args.keys() and all(
                same(value, right.args[key]) for key, value in left.args.items())
        if isinstance(left, list):
            return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
        return left == right
    try:
        return same(parse_one(original, read=dialect), parse_one(replacement, read=dialect))
    except (ParseError, ValueError, AttributeError):
        return False
