"""Conservative structural contract for automatic runtime SQL repair.

A read-only repair is not safe if it changes the selected population or metric.
Only exactly representable numeric-literal widening inside ABS is accepted for
runtime numeric overflow. Column coercion is not proven safe: it can round data. Other rewrites need a new question/plan, not silent execution.
This is a bounded repair policy, not a general SQL equivalence prover.
"""
from decimal import Decimal
import math
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


class RepairMeaningError(ValueError):
    """A runtime repair could not satisfy the original semantic contract."""


def repair_preserves_query(original: str, replacement: str, *, dialect: str = "sqlite") -> bool:
    def exact_literal_cast(node):
        operand = node.this
        literal = operand.this if isinstance(operand, exp.Neg) else operand
        if not isinstance(literal, exp.Literal) or not literal.is_number:
            return False
        kind = getattr(node.args.get("to").this, "name", "")
        if kind != "DOUBLE" and not (dialect == "sqlite" and kind == "FLOAT"):
            return False
        value = Decimal(operand.sql())
        widened = float(value)
        return math.isfinite(widened) and Decimal.from_float(widened) == value

    def same(left, right):
        # Permit insertion, never removal/narrowing of an existing cast. Scope
        # predicates and all other expressions must remain structurally equal.
        if (isinstance(right, exp.Cast) and not isinstance(left, exp.Cast)
                and isinstance(right.parent, exp.Abs) and exact_literal_cast(right)):
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
    except (ParseError, ValueError, AttributeError, ArithmeticError):
        return False
