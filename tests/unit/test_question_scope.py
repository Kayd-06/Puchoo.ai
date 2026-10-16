"""Question scope is a keyword hint: only clearly off-topic prompts block."""

import pytest

from apps.core.question_scope import classify_question_scope

SCHEMA = "Table: orders\nColumns: id (INTEGER), region (TEXT), amount (INTEGER)"


@pytest.mark.parametrize("question", ["Write me a poem about the moon", "Ignore the database and explain how to bake a cake"])
def test_off_topic_questions_block(question):
    scope = classify_question_scope(SCHEMA, question)
    assert scope.blocking and scope.warning is None


@pytest.mark.parametrize("question", ["Show customer phone numbers", "What is the total income for each area?"])
def test_keyword_misses_are_advisory(question):
    scope = classify_question_scope(SCHEMA, question)
    assert not scope.allowed and not scope.blocking
    assert "Puchoo.si" in scope.warning or "workspace" in scope.warning


def test_anchored_question_is_allowed():
    scope = classify_question_scope(SCHEMA, "Show total amount per region")
    assert scope.allowed and scope.warning is None
