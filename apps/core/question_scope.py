"""Deterministic workspace-data relevance checks for analytics questions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.core.semantic_layer import parse_schema


@dataclass(frozen=True)
class QuestionScope:
    allowed: bool
    reason: str | None = None


_STOP_WORDS = {
    "a", "about", "all", "an", "and", "are", "as", "at", "be", "by",
    "can", "could", "data", "database", "do", "for", "from", "give", "has",
    "have", "i", "in", "is", "it", "me", "my", "of", "on", "our", "please",
    "show", "tell", "that", "the", "their", "this", "to", "today", "was",
    "were", "what", "when", "where", "which", "who", "with", "workspace",
}

_ANALYTICS_PATTERN = re.compile(
    r"\b(?:show|list|find|report|display|summari[sz]e|count|total|sum|average|avg|"
    r"minimum|maximum|min|max|trend|compare|comparison|breakdown|rank|top|bottom|"
    r"highest|lowest|most|least|how\s+many|how\s+much|monthly|weekly|daily|yearly|"
    r"quarterly|revenue|sales|expense|expenses|cost|costs|profit|attendance|marks?|"
    r"fees?|orders?|invoices?|employees?|students?|customers?|products?)\b",
    re.IGNORECASE,
)

_NON_DATA_PATTERN = re.compile(
    r"\b(?:poem|story|joke|recipe|horoscope|weather|news|president|capital\s+of|"
    r"bake|cook|translate|write\s+(?:an?\s+)?(?:email|essay|code|song)|"
    r"ignore\s+(?:the\s+)?(?:database|schema|instructions?))\b",
    re.IGNORECASE,
)


def _variants(token: str) -> set[str]:
    values = {token}
    if token.endswith("ies") and len(token) > 4:
        values.add(token[:-3] + "y")
    elif token.endswith("es") and len(token) > 4:
        values.add(token[:-2])
    elif token.endswith("s") and len(token) > 3:
        values.add(token[:-1])
    return values


def _tokens(value: str) -> set[str]:
    result: set[str] = set()
    for token in re.findall(r"[a-z][a-z0-9]+", value.lower().replace("_", " ")):
        if len(token) >= 3 and token not in _STOP_WORDS:
            result.update(_variants(token))
    return result


def classify_question_scope(schema: str, question: str) -> QuestionScope:
    """Allow only analytical questions anchored to the active schema."""

    if _NON_DATA_PATTERN.search(question):
        return QuestionScope(False, "unrelated")

    schema_tokens: set[str] = set()
    for table in parse_schema(schema):
        schema_tokens.update(_tokens(table.name))
        for column in table.columns:
            schema_tokens.update(_tokens(column))

    question_tokens = _tokens(question)
    has_schema_anchor = bool(question_tokens & schema_tokens)
    has_analytics_intent = bool(_ANALYTICS_PATTERN.search(question))
    unmatched_tokens = {
        token for token in question_tokens if not (_variants(token) & schema_tokens)
    }

    if has_schema_anchor and (has_analytics_intent or not unmatched_tokens):
        return QuestionScope(True)
    if has_analytics_intent:
        return QuestionScope(False, "missing_data")
    return QuestionScope(False, "unrelated")


__all__ = ["QuestionScope", "classify_question_scope"]
