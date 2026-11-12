import pytest
from apps.core.clarifications import resolve_clarifications
from apps.core.llm_client import question_clarification

SCHEMA = "orders(id, amount, region, issued_date); students(id, class_id, marks, attendance, fees, enrollment)"
QUESTIONS = [
    "Classify students improving stable declining using marks attendance fees and enrollment in class 10 in 2025",
    "Classify students improving stable declining using marks and attendance in class 10 in 2025",
    "Which students are doing well in class 10 in 2025?",
    "Show students with higher attendance in class 10 in 2025",
    "Show students eligible for scholarship in class 10 in 2025",
    "Show total amount in fiscal year 2025 for region west",
    "Show best customers in region west in 2025",
    "Show profit in region west in 2025",
    "Show amount in fiscal quarter 2025 for region west",
    "Show amount in fiscal month 2025 for region west",
]
CASES = [(question, question_clarification(SCHEMA, question), choice)
         for question in QUESTIONS
         for choice in question_clarification(SCHEMA, question)["suggestions"]]

@pytest.mark.parametrize('question,offered,choice', CASES)
def test_every_offered_choice_progresses_without_erasing_scope(question, offered, choice):
    planned, next_step = resolve_clarifications(SCHEMA, question, [{"reason": offered["reason"], "choice": choice}])
    assert "2025" in planned
    assert ("class 10" in planned) if "class 10" in question else ("region west" in planned)
    assert next_step is None or next_step['reason'] != offered['reason']
    if next_step and next_step['reason'].endswith('_required'):
        assert next_step['suggestions'] == []  # Missing rules cannot authorize SQL.


def test_factor_choice_then_definition_replays_both_steps():
    question = QUESTIONS[0]
    first = question_clarification(SCHEMA, question)
    answers = [{"reason": first['reason'], "choice": first['suggestions'][0]}]
    _, second = resolve_clarifications(SCHEMA, question, answers)
    assert second['reason'] == 'missing_performance_classification_definition'
    answers.append({"reason": second['reason'], "choice": second['suggestions'][0]})
    planned, last = resolve_clarifications(SCHEMA, question, answers)
    assert last is None
    assert 'class 10 in 2025' in planned
    assert 'latest 90 days' in planned and '+5 points' in planned


def test_calendar_choice_only_changes_calendar_and_does_not_leave_fiscal_trigger():
    planned, next_step = resolve_clarifications(SCHEMA, QUESTIONS[5], [{"reason": 'missing_time_definition', "choice": 'Use calendar year instead'}])
    assert planned == 'Show total amount in calendar year 2025 for region west'
    assert next_step is None


@pytest.mark.parametrize('answer', [
    {"reason": 'missing_time_definition', "choice": 'DROP TABLE orders'},
    {"reason": 'ambiguous_metric', "choice": 'Use calendar year instead'},
])
def test_unoffered_or_stale_answer_is_not_a_bypass(answer):
    with pytest.raises(ValueError):
        resolve_clarifications(SCHEMA, QUESTIONS[5], [answer])


def test_detail_request_cannot_be_bypassed_by_extra_answers():
    first = question_clarification(SCHEMA, QUESTIONS[2])
    with pytest.raises(ValueError):
        resolve_clarifications(SCHEMA, QUESTIONS[2], [{"reason": first['reason'], "choice": first['suggestions'][0]}] * 2)


@pytest.mark.parametrize('metric', ['average marks above 80', 'overall attendance >= 90'])
def test_user_can_supply_requested_metric_rule_without_repeating_choice(metric):
    question = f'Show students doing well with {metric} in class 10 in 2025'
    planned, clarification = resolve_clarifications(SCHEMA, question, [])
    assert planned == question and clarification is None


@pytest.mark.parametrize('literal', ["'fiscal year'", '\"fiscal year\"', '‘fiscal year’', '“fiscal year”'])
def test_calendar_resolution_never_rewrites_quoted_region_filter(literal):
    question = 'Show amount in fiscal year 2025 for region ' + literal
    planned, next_step = resolve_clarifications(SCHEMA, question, [{'reason': 'missing_time_definition', 'choice': 'Use calendar year instead'}])
    assert planned == 'Show amount in calendar year 2025 for region ' + literal
    assert next_step is None


def test_quoted_data_cannot_supply_missing_academic_threshold():
    step = question_clarification(SCHEMA, "Show students doing well in class 10 where label = 'average marks above 80'")
    assert step['reason'] == 'ambiguous_education_metric'


@pytest.mark.parametrize('period', ['quarter', 'month'])
def test_calendar_choice_preserves_requested_period_granularity(period):
    question = f'Show amount in fiscal {period} 2025 for region west'
    offered = question_clarification(SCHEMA, question)
    choice = f'Use calendar {period} instead'
    assert choice in offered['suggestions']
    planned, next_step = resolve_clarifications(SCHEMA, question, [{'reason': offered['reason'], 'choice': choice}])
    assert planned == question.replace('fiscal '+period, 'calendar '+period)
    assert next_step is None

def test_scholarship_fee_adjustment_is_not_an_eligibility_request():
    assert question_clarification(SCHEMA, 'Which school classes have the highest outstanding fees after accounting for scholarship adjustments and payment deadlines?') is None


def test_attendance_marks_relationship_does_not_need_a_comparison_baseline():
    assert question_clarification(SCHEMA, 'Do students with better attendance achieve higher marks after accounting for previous academic performance and class level?') is None


def test_missing_data_check_runs_before_vague_metric_rules():
    clarification = question_clarification(SCHEMA, 'Which students are doing well and what is the profit?')
    assert clarification['reason'] == 'concept_not_in_data'


def test_vague_questions_still_offer_choice_buttons():
    for question, reason in (
        ('Show the best region', 'ambiguous_metric'),
        ('Which students are doing well in class 10?', 'ambiguous_education_metric'),
        ('Show students with higher attendance in class 10', 'missing_comparison_baseline'),
    ):
        clarification = question_clarification(SCHEMA, question)
        assert clarification['reason'] == reason
        assert clarification['suggestions']
