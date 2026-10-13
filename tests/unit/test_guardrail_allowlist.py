"""Allow/deny matrix for the SQL guardrail allowlist (H3)."""

from __future__ import annotations

import pytest

pytest.importorskip("sqlglot")

from apps.core.guardrails import (  # noqa: E402
    DANGEROUS_FUNCTIONS,
    SchemaCatalog,
    SQLGuardrailError,
    SQLGuardrails,
)

DIALECTS = ("sqlite", "postgresql", "mysql")

CATALOG = SchemaCatalog.from_mapping(
    {
        "orders": ["id", "customer_id", "amount", "status", "created_at", "region"],
        "customers": ["id", "name", "email", "city", "signup_date"],
    },
)


def guard(dialect: str, catalog: SchemaCatalog | None = CATALOG, max_limit: int = 500) -> SQLGuardrails:
    return SQLGuardrails(max_limit=max_limit, dialect=dialect, catalog=catalog)


ALLOWED_COMMON = [
    "SELECT id, amount FROM orders",
    "SELECT COUNT(*) AS n FROM orders",
    "SELECT status, SUM(amount) AS total, AVG(amount), MIN(amount), MAX(amount) FROM orders GROUP BY status ORDER BY total DESC",
    "SELECT o.id, c.name FROM orders AS o JOIN customers AS c ON c.id = o.customer_id WHERE o.amount > 10",
    "WITH totals AS (SELECT customer_id, SUM(amount) AS total FROM orders GROUP BY customer_id) SELECT c.name, t.total FROM totals AS t JOIN customers AS c ON c.id = t.customer_id",
    "SELECT id FROM orders UNION ALL SELECT id FROM customers",
    "SELECT id FROM orders INTERSECT SELECT customer_id FROM orders",
    "SELECT id FROM orders EXCEPT SELECT customer_id FROM orders",
    "SELECT * FROM (SELECT id, amount FROM orders WHERE amount > (SELECT AVG(amount) FROM orders)) AS big",
    "SELECT id FROM orders WHERE customer_id IN (SELECT id FROM customers WHERE city = 'Pune')",
    "SELECT id FROM orders AS o WHERE EXISTS (SELECT 1 FROM customers AS c WHERE c.id = o.customer_id)",
    "SELECT CASE WHEN amount > 100 THEN 'big' ELSE 'small' END AS size FROM orders",
    "SELECT COALESCE(region, 'unknown'), NULLIF(amount, 0), CAST(amount AS INTEGER) FROM orders",
    "SELECT ROW_NUMBER() OVER (PARTITION BY region ORDER BY amount DESC) AS rn, RANK() OVER (ORDER BY amount) FROM orders",
    "SELECT DENSE_RANK() OVER (ORDER BY amount), NTILE(4) OVER (ORDER BY amount), LAG(amount) OVER (ORDER BY id), LEAD(amount) OVER (ORDER BY id) FROM orders",
    "SELECT LOWER(name), UPPER(city), LENGTH(email), TRIM(name), REPLACE(email, '@', ' at ') FROM customers",
    "SELECT ABS(amount), ROUND(amount, 2), FLOOR(amount), CEIL(amount), amount % 2 FROM orders",
    "SELECT region, COUNT(DISTINCT customer_id) FROM orders GROUP BY region HAVING COUNT(*) > 1",
    "SELECT id FROM orders ORDER BY id LIMIT 10 OFFSET 5",
    "SELECT 'pg_sleep(1)' AS literal_text FROM orders",
    "SELECT id FROM orders -- top orders\n",
    "SELECT /* plain note */ id FROM orders",
    "SELECT name FROM customers WHERE name = 'पुणे'",
]

ALLOWED_BY_DIALECT = {
    "sqlite": [
        "SELECT strftime('%Y-%m', created_at) AS month, SUM(amount) FROM orders GROUP BY month",
        "SELECT date(created_at), julianday('now') - julianday(created_at), IFNULL(region, 'x'), substr(name, 1, 3), instr(email, '@'), total(amount) FROM orders JOIN customers ON customers.id = orders.customer_id",
        "SELECT * FROM main.orders",
        "SELECT round(amount, 2), iif(amount > 1, 1, 0) FROM orders",
    ],
    "postgresql": [
        "SELECT DATE_TRUNC('month', created_at) AS month, SUM(amount) FROM orders GROUP BY 1",
        "SELECT EXTRACT(YEAR FROM created_at), TO_CHAR(created_at, 'YYYY-MM'), NOW(), CURRENT_DATE, created_at + INTERVAL '1 day' FROM orders",
        "SELECT STRING_AGG(name, ', '), PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount) FROM orders JOIN customers ON customers.id = orders.customer_id",
        "SELECT amount::numeric, created_at::date, name ILIKE '%a%', AGE(created_at), DATE_PART('year', created_at) FROM orders JOIN customers ON customers.id = orders.customer_id",
        "SELECT * FROM public.orders",
        "SELECT id FROM orders FETCH FIRST 5 ROWS ONLY",
    ],
    "mysql": [
        "SELECT DATE_FORMAT(created_at, '%Y-%m') AS month, SUM(amount) FROM orders GROUP BY month",
        "SELECT YEAR(created_at), MONTH(created_at), DATEDIFF(NOW(), created_at), DATE_ADD(created_at, INTERVAL 1 DAY), CURDATE(), DAYNAME(created_at) FROM orders",
        "SELECT IFNULL(region, 'x'), IF(amount > 1, 1, 0), GROUP_CONCAT(id), TIMESTAMPDIFF(DAY, created_at, NOW()) FROM orders",
        "SELECT `id` FROM `orders`",
    ],
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("sql", ALLOWED_COMMON)
def test_common_read_queries_are_allowed(dialect, sql):
    if dialect == "mysql" and ("INTERSECT" in sql or "EXCEPT" in sql):
        pytest.skip("MySQL 8.0.31+ only; covered by the other dialects")
    guarded = guard(dialect).validate_and_clamp(sql)
    assert "LIMIT" in guarded.sql.upper() or "FETCH" in guarded.sql.upper()
    # Idempotent: the approved SQL re-validates byte-for-byte.
    assert guard(dialect).validate_exact(guarded.sql).sql == guarded.sql


@pytest.mark.parametrize(
    "dialect,sql",
    [(dialect, sql) for dialect, queries in ALLOWED_BY_DIALECT.items() for sql in queries],
)
def test_dialect_specific_read_queries_are_allowed(dialect, sql):
    guarded = guard(dialect).validate_and_clamp(sql)
    assert guard(dialect).validate_exact(guarded.sql).sql == guarded.sql


DANGEROUS_CALLS = {
    "postgresql": [
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_read_binary_file('/etc/passwd')",
        "SELECT * FROM pg_ls_dir('.')",
        "SELECT pg_ls_dir('.')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT lo_export(1, '/tmp/x')",
        "SELECT dblink('host=evil', 'select 1')",
        "SELECT * FROM dblink('host=evil', 'select 1') AS t(a int)",
        "SELECT dblink_exec('host=evil', 'drop table x')",
        "SELECT set_config('default_transaction_read_only', 'off', false)",
        "SELECT current_setting('data_directory')",
        "SELECT query_to_xml('delete from orders', true, true, '')",
        "SELECT nextval('orders_id_seq')",
        "SELECT version()",
        "SELECT pg_terminate_backend(1)",
        "SELECT txid_current()",
        "SELECT current_user",
        "SELECT * FROM generate_series(1, 100000000)",
        "SELECT pg_catalog.pg_sleep(1)",
        "SELECT \"pg_sleep\"(1)",
        "SELECT PG_SLEEP(1)",
        "SELECT Pg_Sleep(1)",
        "SELECT pg_catalog.upper('a')",
        "SELECT 'orders'::regclass",
        "SELECT id FROM orders WHERE id = (SELECT pg_sleep(5))",
        "WITH x AS (SELECT pg_sleep(5)) SELECT * FROM x",
        "SELECT id FROM orders UNION SELECT pg_sleep(1)",
        "SELECT regexp_replace(name, 'a', 'b') FROM customers",
    ],
    "mysql": [
        "SELECT SLEEP(10)",
        "SELECT sleep(10)",
        "SELECT BENCHMARK(100000000, MD5('a'))",
        "SELECT LOAD_FILE('/etc/passwd')",
        "SELECT GET_LOCK('a', 10)",
        "SELECT @@version",
        "SELECT @@global.secure_file_priv",
        "SELECT USER()",
        "SELECT DATABASE()",
        "SELECT VERSION()",
        "SELECT extractvalue(1, 'x')",
        "SELECT updatexml(1, 'x', 'y')",
        "SELECT id FROM orders WHERE id = (SELECT SLEEP(5))",
        "SELECT id FROM orders WHERE amount > (SELECT BENCHMARK(1, 1))",
    ],
    "sqlite": [
        "SELECT load_extension('/tmp/evil.so')",
        "SELECT readfile('/etc/passwd')",
        "SELECT writefile('/tmp/x', 'y')",
        "SELECT edit('x')",
        "SELECT fts3_tokenizer('simple')",
        "SELECT randomblob(1000000000)",
        "SELECT zeroblob(1000000000)",
        "SELECT sqlite_version()",
        "SELECT * FROM pragma_table_info('orders')",
        "SELECT * FROM json_each('[1,2]')",
        "SELECT LOAD_EXTENSION('x')",
    ],
}


@pytest.mark.parametrize(
    "dialect,sql",
    [(dialect, sql) for dialect, queries in DANGEROUS_CALLS.items() for sql in queries],
)
def test_dangerous_functions_are_rejected(dialect, sql):
    for catalog in (CATALOG, None):
        with pytest.raises(SQLGuardrailError):
            guard(dialect, catalog).validate_and_clamp(sql)


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "sqlite"])
def test_every_listed_dangerous_function_is_rejected(dialect):
    for name in sorted(DANGEROUS_FUNCTIONS[dialect] | DANGEROUS_FUNCTIONS["*"]):
        with pytest.raises(SQLGuardrailError):
            guard(dialect, None).validate_and_clamp(f"SELECT {name}(1) FROM orders")


@pytest.mark.parametrize("dialect", DIALECTS)
def test_unknown_functions_are_rejected_by_default(dialect):
    for sql in (
        "SELECT some_custom_udf(amount) FROM orders",
        "SELECT xp_cmdshell('dir')",
        "SELECT md5(name) FROM customers",
        "SELECT uuid()",
        "SELECT random()",
    ):
        with pytest.raises(SQLGuardrailError, match="not on Puchoo.si's list|blocked"):
            guard(dialect).validate_and_clamp(sql)


SYSTEM_ACCESS = {
    "postgresql": [
        "SELECT * FROM pg_catalog.pg_user",
        "SELECT * FROM pg_user",
        "SELECT * FROM pg_shadow",
        "SELECT usename, passwd FROM pg_catalog.pg_shadow",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM INFORMATION_SCHEMA.COLUMNS",
        "SELECT * FROM \"pg_catalog\".\"pg_roles\"",
        "SELECT * FROM pg_stat_activity",
        "SELECT * FROM orders AS o JOIN pg_settings AS s ON true",
        "SELECT * FROM other_schema.orders",
        "SELECT * FROM otherdb.public.orders",
        "SELECT id FROM orders WHERE id IN (SELECT oid FROM pg_class)",
        "WITH pg_user AS (SELECT 1 AS a) SELECT * FROM pg_user",
    ],
    "mysql": [
        "SELECT * FROM mysql.user",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM performance_schema.threads",
        "SELECT * FROM sys.version",
        "SELECT * FROM `mysql`.`user`",
        "SELECT * FROM otherdb.orders",
    ],
    "sqlite": [
        "SELECT * FROM sqlite_master",
        "SELECT sql FROM sqlite_schema",
        "SELECT * FROM SQLITE_MASTER",
        "SELECT * FROM sqlite_temp_master",
        "SELECT * FROM temp.orders",
        "SELECT * FROM attached_db.orders",
        "SELECT name FROM \"sqlite_master\"",
    ],
}


@pytest.mark.parametrize(
    "dialect,sql",
    [(dialect, sql) for dialect, queries in SYSTEM_ACCESS.items() for sql in queries],
)
def test_system_schemas_and_tables_are_rejected(dialect, sql):
    for catalog in (CATALOG, None):
        with pytest.raises(SQLGuardrailError):
            guard(dialect, catalog).validate_and_clamp(sql)


WRITE_OR_LOCK = {
    "postgresql": [
        "SELECT * INTO backup FROM orders",
        "SELECT * FROM orders FOR UPDATE",
        "SELECT * FROM orders FOR SHARE",
        "SELECT * FROM orders FOR NO KEY UPDATE",
        "WITH d AS (DELETE FROM orders RETURNING id) SELECT * FROM d",
        "WITH u AS (UPDATE orders SET amount = 0 RETURNING id) SELECT * FROM u",
        "WITH i AS (INSERT INTO orders (id) VALUES (1) RETURNING id) SELECT * FROM i",
        "COPY orders TO '/tmp/x'",
        "SET statement_timeout = 0",
        "SET TRANSACTION READ WRITE",
        "BEGIN",
        "VACUUM",
        "EXPLAIN ANALYZE SELECT 1",
        "SELECT 1; DROP TABLE orders",
        "SELECT 1; SELECT 2",
        "DELETE FROM orders",
        "CREATE TABLE x AS SELECT * FROM orders",
        "TABLE orders",
        "VALUES (1)",
        "SELECT id FROM orders WHERE id = :id",
        "SELECT id FROM orders WHERE id = $1",
        "SELECT id FROM orders WHERE id = ?",
    ],
    "mysql": [
        "SELECT * FROM orders INTO OUTFILE '/tmp/x'",
        "SELECT * FROM orders INTO DUMPFILE '/tmp/x'",
        "SELECT * INTO OUTFILE '/tmp/x' FROM orders",
        "SELECT id INTO @v FROM orders",
        "SELECT * FROM orders LOCK IN SHARE MODE",
        "SELECT * FROM orders FOR UPDATE",
        "SELECT 1 /*!50000 , SLEEP(5) */",
        "SELECT /*!50000 SLEEP(5), */ id FROM orders",
        "SELECT /*+ MAX_EXECUTION_TIME(100000000) */ id FROM orders",
        "SELECT /*M!100000 SLEEP(5), */ id FROM orders",
        "SELECT 1; SELECT SLEEP(1)",
        "LOAD DATA INFILE '/etc/passwd' INTO TABLE orders",
        "HANDLER orders OPEN",
        "SET SESSION TRANSACTION READ WRITE",
        "SELECT @a := 1",
    ],
    "sqlite": [
        "ATTACH DATABASE '/tmp/evil.db' AS evil",
        "PRAGMA query_only = OFF",
        "PRAGMA writable_schema = ON",
        "SELECT 1; DELETE FROM orders",
        "INSERT INTO orders (id) VALUES (1)",
        "REPLACE INTO orders (id) VALUES (1)",
        "VACUUM INTO '/tmp/copy.db'",
        "WITH d AS (DELETE FROM orders RETURNING id) SELECT * FROM d",
    ],
}


@pytest.mark.parametrize(
    "dialect,sql",
    [(dialect, sql) for dialect, queries in WRITE_OR_LOCK.items() for sql in queries],
)
def test_writes_locks_multi_statements_and_smuggling_are_rejected(dialect, sql):
    for catalog in (CATALOG, None):
        with pytest.raises(SQLGuardrailError):
            guard(dialect, catalog).validate_and_clamp(sql)


def test_plain_comments_are_stripped_from_the_sql_that_runs():
    guarded = guard("postgresql").validate_and_clamp("SELECT id /* note */ FROM orders -- trailing\n")
    assert "/*" not in guarded.sql and "--" not in guarded.sql
    assert guarded.sql == "SELECT id FROM orders LIMIT 500"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM orders WHERE name = 'a\u202e'",  # right-to-left override
        "SELECT id FROM orders\u200b",  # zero-width space
        "SELECT\u00a0id FROM orders",  # no-break space
        "SELECT id FROM orders WHERE x = 'a\x00'",
        "SELECT \ufeffid FROM orders",
    ],
)
def test_invisible_and_control_characters_are_rejected(sql):
    with pytest.raises(SQLGuardrailError, match="invisible or control"):
        guard("postgresql").validate_and_clamp(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sl\u0435ep(1)",  # Cyrillic e homoglyph
        "SELECT ｐｇ_sleep(1)",  # fullwidth letters
    ],
)
def test_unicode_lookalike_function_names_are_rejected(sql):
    with pytest.raises(SQLGuardrailError):
        guard("postgresql").validate_and_clamp(sql)


@pytest.mark.parametrize("dialect", DIALECTS)
def test_tables_and_columns_must_exist_in_the_active_source(dialect):
    g = guard(dialect)
    with pytest.raises(SQLGuardrailError, match="table secrets is not part"):
        g.validate_and_clamp("SELECT * FROM secrets")
    with pytest.raises(SQLGuardrailError, match="column password_hash is not part"):
        g.validate_and_clamp("SELECT password_hash FROM customers")
    with pytest.raises(SQLGuardrailError, match="table secrets"):
        g.validate_and_clamp("SELECT id FROM orders WHERE id IN (SELECT id FROM secrets)")
    with pytest.raises(SQLGuardrailError, match="table secrets"):
        g.validate_and_clamp("WITH x AS (SELECT * FROM secrets) SELECT * FROM x")
    # Aliases, CTE names and derived columns are fine.
    g.validate_and_clamp(
        "WITH totals AS (SELECT customer_id AS cid, SUM(amount) AS total FROM orders GROUP BY customer_id) "
        "SELECT cid, total AS grand FROM totals ORDER BY grand"
    )
    if dialect == "sqlite":
        # sqlglot cannot render SQLite CTE column lists; refuse rather than run
        # SQL whose meaning silently changed.
        with pytest.raises(SQLGuardrailError, match="feature"):
            g.validate_and_clamp("WITH totals (cid) AS (SELECT customer_id FROM orders) SELECT cid FROM totals")
        return
    g.validate_and_clamp(
        "WITH totals (cid, total) AS (SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id) "
        "SELECT cid, total AS grand FROM totals ORDER BY grand"
    )
    # Names are case-insensitive.
    g.validate_and_clamp("SELECT ID, Amount FROM ORDERS")


def test_system_columns_are_rejected_when_the_schema_is_known():
    for dialect, sql in (
        ("sqlite", "SELECT rowid FROM orders"),
        ("postgresql", "SELECT ctid, xmin FROM orders"),
    ):
        with pytest.raises(SQLGuardrailError, match="column"):
            guard(dialect).validate_and_clamp(sql)


def test_without_a_catalog_only_tables_policy_applies():
    guarded = guard("sqlite", None).validate_and_clamp("SELECT anything FROM whatever")
    assert guarded.sql == "SELECT anything FROM whatever LIMIT 500"


def test_union_limit_is_clamped_on_the_outer_query():
    guarded = guard("postgresql", max_limit=50).validate_and_clamp(
        "SELECT id FROM orders UNION SELECT id FROM customers LIMIT 1000"
    )
    assert guarded.sql.endswith("LIMIT 50")
    assert guarded.sql.count("LIMIT") == 1
    assert guarded.limit == 50 and guarded.limit_clamped


def test_validate_exact_refuses_sql_that_would_change():
    g = guard("sqlite", max_limit=10)
    with pytest.raises(SQLGuardrailError, match="no longer matches"):
        g.validate_exact("SELECT id FROM orders")
    with pytest.raises(SQLGuardrailError, match="no longer matches"):
        g.validate_exact("SELECT id FROM orders LIMIT 500")
    assert g.validate_exact("SELECT id FROM orders LIMIT 10").sql == "SELECT id FROM orders LIMIT 10"


def test_error_messages_are_user_facing():
    with pytest.raises(SQLGuardrailError) as caught:
        guard("postgresql").validate_and_clamp("SELECT pg_sleep(1)")
    assert "pg_sleep" in str(caught.value)
    assert "Traceback" not in str(caught.value)
    with pytest.raises(SQLGuardrailError) as caught:
        guard("postgresql").validate_and_clamp("SELECT * FROM pg_catalog.pg_user")
    assert "System schemas" in str(caught.value)


def test_overlong_and_deeply_nested_sql_is_rejected():
    with pytest.raises(SQLGuardrailError):
        guard("sqlite", None).validate_and_clamp("SELECT " + " + ".join(["1"] * 10_000))
    nested = "SELECT * FROM " + "(SELECT * FROM " * 400 + "orders" + ") AS x" * 400
    with pytest.raises(SQLGuardrailError):
        guard("sqlite", None).validate_and_clamp(nested)


def test_formatting_functions_that_can_allocate_huge_strings_are_rejected():
    for dialect, sql in (
        ("sqlite", "SELECT printf('%999999999d', 1)"),
        ("sqlite", "SELECT format('%s', id) FROM orders"),
        ("postgresql", "SELECT repeat('a', 1000000000)"),
        ("postgresql", "SELECT lpad(name, 1000000000) FROM customers"),
        ("mysql", "SELECT REPEAT('a', 1000000000)"),
    ):
        with pytest.raises(SQLGuardrailError):
            guard(dialect).validate_and_clamp(sql)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT session_user",
        "SELECT user",
        "SELECT current_role",
        "SELECT current_catalog",
        "SELECT current_schema",
        "SELECT SESSION_USER FROM orders",
        "SELECT id FROM orders WHERE user = 'postgres'",
    ],
)
def test_session_keywords_that_look_like_columns_are_rejected(dialect, sql):
    # PostgreSQL evaluates these bare keywords as session functions.
    for catalog in (CATALOG, None):
        with pytest.raises(SQLGuardrailError):
            guard(dialect, catalog).validate_and_clamp(sql)


def test_quoted_session_keyword_columns_are_allowed_when_they_exist():
    catalog = SchemaCatalog.from_mapping({"logins": ["id", "user"]})
    guard("postgresql", catalog).validate_and_clamp('SELECT "user" FROM logins')
    guard("postgresql", catalog).validate_and_clamp('SELECT logins.user FROM logins')


@pytest.mark.parametrize("dialect", DIALECTS)
def test_sqlite_in_table_shorthand_is_rejected(dialect):
    for sql in (
        "SELECT id FROM orders WHERE id IN customers",
        "SELECT id FROM orders WHERE status IN sqlite_master",
        "SELECT id FROM orders WHERE status IN main.sqlite_master",
    ):
        for catalog in (CATALOG, None):
            with pytest.raises(SQLGuardrailError):
                guard(dialect, catalog).validate_and_clamp(sql)


@pytest.mark.parametrize("sql", ["SELECT id FROM orders WHERE id = $x", "SELECT id FROM orders WHERE id = @x"])
def test_parameter_like_identifiers_are_rejected_without_a_catalog(sql):
    with pytest.raises(SQLGuardrailError):
        guard("sqlite", None).validate_and_clamp(sql)


def test_sqlite_virtual_system_tables_are_rejected():
    for sql in ("SELECT * FROM dbstat", "SELECT * FROM sqlite_dbpage", "SELECT * FROM \"main\".\"sqlite_master\""):
        for catalog in (CATALOG, None):
            with pytest.raises(SQLGuardrailError):
                guard("sqlite", catalog).validate_and_clamp(sql)


def test_schema_qualifiers_follow_each_dialects_identifier_rules():
    pg = SchemaCatalog.from_mapping({"orders": ["id"]}, qualifiers=["public"])
    for sql in ("SELECT id FROM public.orders", "SELECT id FROM PUBLIC.orders", 'SELECT id FROM "public"."orders"'):
        guard("postgresql", pg).validate_and_clamp(sql)
    # Quoted PostgreSQL names keep their case, so "Public" is another schema.
    for sql in ('SELECT id FROM "Public".orders', 'SELECT id FROM "PUBLIC".orders', "SELECT id FROM reporting.orders"):
        with pytest.raises(SQLGuardrailError, match="schema"):
            guard("postgresql", pg).validate_and_clamp(sql)

    # A source whose default schema is not public cannot reach public.
    analytics = SchemaCatalog.from_mapping({"orders": ["id"]}, qualifiers=["analytics"])
    guard("postgresql", analytics).validate_and_clamp("SELECT id FROM analytics.orders")
    with pytest.raises(SQLGuardrailError, match="schema"):
        guard("postgresql", analytics).validate_and_clamp("SELECT id FROM public.orders")

    # MySQL database names may be case-sensitive: require an exact match.
    my = SchemaCatalog.from_mapping({"orders": ["id"]}, qualifiers=["reporting"])
    guard("mysql", my).validate_and_clamp("SELECT id FROM `reporting`.`orders`")
    for sql in ("SELECT id FROM REPORTING.orders", "SELECT id FROM other.orders"):
        with pytest.raises(SQLGuardrailError, match="schema"):
            guard("mysql", my).validate_and_clamp(sql)

    # SQLite schema names are case-insensitive; only main is the source.
    sl = SchemaCatalog.from_mapping({"orders": ["id"]}, qualifiers=["main"])
    for sql in ("SELECT id FROM main.orders", "SELECT id FROM MAIN.orders", 'SELECT id FROM "Main".orders'):
        guard("sqlite", sl).validate_and_clamp(sql)


def test_collations_are_allowed():
    guard("sqlite").validate_and_clamp("SELECT id FROM orders WHERE status = 'paid' COLLATE NOCASE")
    guard("postgresql").validate_and_clamp('SELECT name COLLATE "C" FROM customers ORDER BY 1')


def test_parser_differentials_cannot_smuggle_sql_because_the_rendering_runs():
    # PostgreSQL nests block comments; whatever sqlglot decides, the comment is
    # gone from the SQL that runs, so no hidden call can reach the database.
    guarded = guard("postgresql").validate_and_clamp(
        "SELECT id FROM orders WHERE status = 'x' /* /* nested */ , pg_sleep(1) */"
    )
    assert "pg_sleep" not in guarded.sql and "/*" not in guarded.sql
    # A MySQL backslash-escaped quote stays inside one string literal.
    guarded = guard("mysql").validate_and_clamp("SELECT id FROM orders WHERE status = 'a\\' OR sleep(1) -- '")
    assert guarded.sql == "SELECT id FROM orders WHERE status = 'a'' OR sleep(1) -- ' LIMIT 500"
