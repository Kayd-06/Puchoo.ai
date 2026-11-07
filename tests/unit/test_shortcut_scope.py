"""Unknown constraints must reach planning intact, never an unfiltered template."""
import sqlite3
import pytest
from apps.core.llm_client import canonicalize_analytics_question, schema_guided_fallback_sql

SCHEMA = '''Table: expenses
Columns: expense_date (TEXT), expense_category (TEXT), amount (REAL)

Table: products
Columns: product_id (INTEGER), product_name (TEXT)

Table: invoice_items
Columns: invoice_id (INTEGER), product_id (INTEGER), quantity (INTEGER)

Table: invoices
Columns: invoice_id (INTEGER), invoice_date (TEXT), customer_id (INTEGER), total_amount (REAL), payment_status (TEXT)

Table: customers
Columns: customer_id (INTEGER), customer_name (TEXT)

Table: payments
Columns: invoice_id (INTEGER), amount_paid (REAL)

Table: students
Columns: student_id (INTEGER), full_name (TEXT), class_name (TEXT)

Table: grades
Columns: student_id (INTEGER), assessment_id (INTEGER), marks_obtained (REAL), result_status (TEXT)

Table: assessments
Columns: assessment_id (INTEGER), assessment_date (TEXT), maximum_marks (REAL), course_id (INTEGER)

Table: attendance
Columns: student_id (INTEGER), attendance_date (TEXT), attendance_percentage (REAL)

Table: fees
Columns: student_id (INTEGER), amount_due (REAL), amount_paid (REAL)

Table: enrollments
Columns: student_id (INTEGER), enrollment_date (TEXT), enrollment_status (TEXT)

Table: loans
Columns: student_id (INTEGER), loan_status (TEXT)'''

@pytest.mark.parametrize('question', [
    'Show expenses by category in 2025',
    'Show monthly expenses by category for Travel',
    'Which product sold the most in 2025?',
    'Which product sold the most for customer Alice?',
    'Which product sold the most in region North?',
    'Which product sold the most last month excluding returns?',
    'Show top 5 products by quantity',
    'Tell me which students scored marks greater than 80 percent and give their marks and name in class 10',
    'Tell me which students scored marks greater than 80 percent and give their marks and name in 2025',
    'Top 5 customers by outstanding invoice balance with unpaid invoice count, partial invoice count, total billed amount, total paid amount, and remaining balance',
    'Top customers by outstanding invoice balance with unpaid invoice count, partial invoice count, total billed amount, total paid amount, and remaining balance in 2025',
    'For every student, calculate average marks, marks relative to the course average, overall attendance, attendance relative to the class average, total fees due, total paid, unpaid balance, failed assessment count, overdue library-loan count, and rank students using marks, attendance, and unpaid balance in class 10.',
    'Compare each student average marks percentage and attendance percentage in the latest 90 days with the prior 90 days; average both changes, classify at least +5 points as improving, at most -5 as declining, otherwise stable. Classify using marks and attendance only; show fee-payment behavior and enrollment status separately. Only class 10.',
    'Compare each student average marks percentage and attendance percentage in the latest 90 days with the prior 90 days; weight marks twice attendance, classify at least +5 points as improving, at most -5 as declining, otherwise stable. Classify using marks and attendance only; show fee-payment behavior and enrollment status separately.',
])
def test_extra_constraints_never_match_demo_templates(question):
    normalized = canonicalize_analytics_question(question)
    assert normalized == question
    assert schema_guided_fallback_sql(SCHEMA, normalized) is None


def test_product_year_fixture_has_different_scoped_and_all_time_winners():
    question = 'Which product sold the most in 2025?'
    assert canonicalize_analytics_question(question) == question
    assert schema_guided_fallback_sql(SCHEMA, question) is None
    with sqlite3.connect(':memory:') as db:
        db.executescript('''CREATE TABLE products(product_id INTEGER, product_name TEXT);
        CREATE TABLE invoice_items(invoice_id INTEGER, product_id INTEGER, quantity INTEGER);
        CREATE TABLE invoices(invoice_id INTEGER, invoice_date TEXT);
        INSERT INTO products VALUES(1,'A'),(2,'B');
        INSERT INTO invoices VALUES(1,'2024-01-01'),(2,'2025-01-01');
        INSERT INTO invoice_items VALUES(1,1,100),(2,1,2),(2,2,10);''')
        plain = schema_guided_fallback_sql(SCHEMA, 'Which product sold the most?')
        assert db.execute(plain).fetchone()[1] == 'A'
        scoped = '''SELECT p.product_name FROM products p JOIN invoice_items ii USING(product_id)
        JOIN invoices i USING(invoice_id) WHERE i.invoice_date >= '2025-01-01' AND i.invoice_date < '2026-01-01'
        GROUP BY p.product_id ORDER BY SUM(ii.quantity) DESC LIMIT 1'''
        assert db.execute(scoped).fetchone()[0] == 'B'
