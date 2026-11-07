import pytest
from apps.core.repair_semantics import repair_preserves_query

@pytest.mark.parametrize('dialect', ['sqlite', 'postgres', 'postgresql', 'mysql'])
@pytest.mark.parametrize('suffix', [
    " WHERE class_id = 10 AND issued_date >= '2025-01-01'",
    " WHERE region = 'west' GROUP BY region HAVING SUM(amount) > 100 ORDER BY region LIMIT 3",
])
def test_widening_preserves_every_filter_metric_and_group(dialect, suffix):
    original = 'SELECT ABS(-9223372036854775808) AS magnitude FROM orders' + suffix
    repaired = 'SELECT ABS(CAST(-9223372036854775808 AS DOUBLE PRECISION)) AS magnitude FROM orders' + suffix
    assert repair_preserves_query(original, repaired, dialect=dialect)
    assert not repair_preserves_query(original, 'SELECT amount FROM orders' + suffix, dialect=dialect)
    assert not repair_preserves_query(original, repaired.replace('2025', '2024').replace('west', 'east'), dialect=dialect)

@pytest.mark.parametrize('change', [
    "SELECT SUM(amount) AS total FROM orders WHERE class_id=11 GROUP BY region ORDER BY total DESC LIMIT 3",
    "SELECT AVG(amount) AS total FROM orders WHERE class_id=10 GROUP BY region ORDER BY total DESC LIMIT 3",
    "SELECT SUM(amount) AS total FROM orders WHERE class_id=10 GROUP BY region ORDER BY total ASC LIMIT 3",
    "SELECT SUM(amount) AS total FROM orders WHERE class_id=10 GROUP BY region ORDER BY total DESC LIMIT 5",
    "SELECT SUM(amount) AS total FROM orders WHERE class_id=10 ORDER BY total DESC LIMIT 3",
])
def test_no_filter_metric_ranking_or_group_loss(change):
    original = 'SELECT SUM(amount) AS total FROM orders WHERE class_id=10 GROUP BY region ORDER BY total DESC LIMIT 3'
    assert not repair_preserves_query(original, change)


def test_repair_cannot_remove_existing_cast_or_cast_filter():
    assert not repair_preserves_query('SELECT ABS(CAST(amount AS REAL)) FROM orders', 'SELECT ABS(amount) FROM orders')
    assert not repair_preserves_query('SELECT amount FROM orders WHERE amount > 10', 'SELECT amount FROM orders WHERE CAST(amount AS REAL) > 10')


@pytest.mark.parametrize('operand', ['amount', '9007199254740993'])
def test_cast_cannot_introduce_unproven_column_or_literal_rounding(operand):
    assert not repair_preserves_query(f'SELECT ABS({operand}) FROM orders', f'SELECT ABS(CAST({operand} AS REAL)) FROM orders')


@pytest.mark.parametrize('original', [
    'SELECT ABS(-9223372036854775808) + 1 FROM orders',
    'SELECT SUM(ABS(-9223372036854775808)) FROM orders',
    'SELECT magnitude + 1 FROM (SELECT ABS(-9223372036854775808) AS magnitude FROM orders) AS x',
    'SELECT ABS(-9223372036854775808) AS magnitude FROM orders HAVING magnitude + 1 > 9223372036854775808',
])
def test_exact_literal_does_not_prove_downstream_arithmetic_or_alias_use(original):
    repaired = original.replace('ABS(-9223372036854775808)', 'ABS(CAST(-9223372036854775808 AS DOUBLE PRECISION))')
    assert not repair_preserves_query(original, repaired, dialect='postgresql')
