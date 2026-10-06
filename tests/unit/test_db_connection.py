"""Connection fields cannot change driver settings or reach internal hosts."""

from __future__ import annotations

import logging
import socket
import ssl
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import certifi
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from apps.core.db_connection import (
    DatabaseConnectionError,
    SecretValue,
    ServerConnection,
    build_server_url,
    checked_connection_host,
    ip_is_blocked,
    materialize_connect_args,
    mysql_connect_args,
    postgres_connect_args,
    render_password_free,
    validate_db_ssl_mode,
)
from apps.core.executor import ReadOnlyExecutor
from apps.core.workspaces import create_server_workspace


def _valid(**overrides):
    payload = {
        "dialect": "postgresql",
        "host": "db.example.com",
        "port": 5432,
        "database": "reporting",
        "username": "readonly",
        "password": "s3cret-db-password",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database", "prod?local_infile=1"),
        ("database", "db#"),
        ("database", "prod%3F"),
        ("database", "app/db"),
        ("host", "x@evil:3306"),
        ("host", "db.example.com/path"),
        ("host", "evil.example?local_infile=1"),
        ("host", "evil.example%3F"),
        ("host", "bad host"),
        ("username", "user name"),
        ("username", "root?local_infile=1"),
        ("username", "db#"),
        ("port", "5432"),
        ("port", "5432?local_infile=1"),
        ("port", True),
        ("port", False),
        ("port", 0),
        ("port", 65536),
    ],
)
def test_injection_attempts_are_rejected(field, value):
    with pytest.raises(ValidationError):
        ServerConnection(**_valid(**{field: value}))


def test_built_url_has_no_query_and_drops_the_password():
    password = "p@ss?word"
    url = build_server_url(
        dialect="mysql",
        username="readonly",
        password=password,
        host="8.8.8.8",
        port=3306,
        database="reporting",
    )
    assert dict(url.query) == {}
    rendered = render_password_free(url)
    assert rendered == "mysql+pymysql://readonly@8.8.8.8:3306/reporting"
    assert "?" not in rendered
    assert password not in rendered
    assert "local_infile" not in rendered


def test_mysql_connect_args_disable_local_infile_and_mask_the_password(monkeypatch):
    monkeypatch.setenv("DB_SSL_REQUIRED", "true")
    monkeypatch.delenv("DB_SSL_CA", raising=False)
    args = mysql_connect_args("s3cret-db-password")
    ca_file = certifi.where()
    assert args["local_infile"] is False
    assert args["ssl"] == {"ca": ca_file}
    assert args["ssl_ca"] == ca_file
    assert args["ssl_verify_cert"] is True
    assert args["ssl_disabled"] is False
    assert args["connect_timeout"] == 10
    assert str(args["password"]) == "***"
    assert "s3cret-db-password" not in repr(args["password"])

    revealed = materialize_connect_args({"local_infile": True, "password": SecretValue("s3cret-db-password")})
    assert revealed["local_infile"] is False
    assert revealed["password"] == "s3cret-db-password"

    monkeypatch.setenv("DB_SSL_REQUIRED", "off")
    disabled = mysql_connect_args("s3cret-db-password")
    assert disabled["local_infile"] is False
    assert disabled["ssl_disabled"] is True
    assert "ssl" not in disabled
    assert "ssl_verify_cert" not in disabled


def test_mysql_driver_receives_verified_tls_kwargs(monkeypatch, tmp_path):
    """The kwargs that reach PyMySQL must require TLS and verify the certificate."""

    ca_file = tmp_path / "mysql-ca.pem"
    ca_file.write_bytes(Path(certifi.where()).read_bytes())
    monkeypatch.setenv("DB_SSL_REQUIRED", "true")
    monkeypatch.setenv("DB_SSL_CA", str(ca_file))
    captured: dict = {}

    def fake_connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        raise RuntimeError("stop before the network")

    import pymysql

    monkeypatch.setattr(pymysql, "connect", fake_connect)
    ready = materialize_connect_args(mysql_connect_args("s3cret-db-password"))
    engine = create_engine(
        "mysql+pymysql://readonly@8.8.8.8:3306/reporting",
        connect_args=ready,
    )
    try:
        with pytest.raises(Exception, match="stop before the network"):
            engine.connect()
    finally:
        engine.dispose()

    kwargs = captured["kwargs"]
    assert kwargs["ssl"] == {"ca": str(ca_file)}
    assert kwargs["ssl_ca"] == str(ca_file)
    assert kwargs["ssl_verify_cert"] is True
    assert kwargs["ssl_disabled"] is False
    assert kwargs["local_infile"] is False
    assert kwargs["password"] == "s3cret-db-password"
    assert kwargs["host"] == "8.8.8.8"

    checked = dict(kwargs)
    checked["defer_connect"] = True
    connection = pymysql.connections.Connection(**checked)
    assert connection._ssl_required is True
    assert connection.ctx.verify_mode == ssl.CERT_REQUIRED
    assert connection.ctx.check_hostname is False
    assert connection._local_infile is False


def test_postgres_connect_args_are_read_only(monkeypatch):
    monkeypatch.delenv("DB_SSL_REQUIRED", raising=False)
    monkeypatch.delenv("DB_SSL_MODE", raising=False)
    monkeypatch.delenv("DB_SSL_ROOT_CERT", raising=False)
    args = postgres_connect_args("s3cret-db-password")
    assert args["sslmode"] == "require"
    assert "sslrootcert" not in args
    assert args["connect_timeout"] == 10
    assert "default_transaction_read_only=on" in args["options"]
    assert "statement_timeout=30000" in args["options"]
    assert str(args["password"]) == "***"


def test_postgres_verify_ca_uses_the_configured_root_cert(monkeypatch):
    monkeypatch.setenv("DB_SSL_REQUIRED", "true")
    monkeypatch.setenv("DB_SSL_MODE", "verify-ca")
    monkeypatch.setenv("DB_SSL_ROOT_CERT", r"C:\certs\root.pem")
    args = postgres_connect_args("s3cret-db-password")
    assert args["sslmode"] == "verify-ca"
    assert args["sslrootcert"] == r"C:\certs\root.pem"


def test_postgres_ssl_mode_is_validated_at_startup_not_per_connection(monkeypatch):
    monkeypatch.setenv("DB_SSL_REQUIRED", "true")
    monkeypatch.setenv("DB_SSL_MODE", "verify-full")
    args = postgres_connect_args("s3cret-db-password")
    assert args["sslmode"] == "verify-full"
    with pytest.raises(ValueError, match="resolved IP"):
        validate_db_ssl_mode()

    monkeypatch.setenv("DB_SSL_MODE", "verify-ca")
    monkeypatch.delenv("DB_SSL_ROOT_CERT", raising=False)
    with pytest.raises(ValueError, match="DB_SSL_ROOT_CERT"):
        validate_db_ssl_mode()
    with pytest.raises(ValueError, match="DB_SSL_ROOT_CERT"):
        postgres_connect_args("s3cret-db-password")

    for mode in ("disable", "allow", "prefer", "require-or-else"):
        monkeypatch.setenv("DB_SSL_MODE", mode)
        with pytest.raises(ValueError, match="require or verify-ca"):
            validate_db_ssl_mode()

    monkeypatch.setenv("DB_SSL_MODE", "require")
    validate_db_ssl_mode()


def test_invalid_db_ssl_mode_stops_process_startup():
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; os.environ['DB_SSL_MODE']='verify-full'; import backend.config",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode != 0
    assert "resolved IP" in completed.stderr


def test_postgres_omits_sslmode_when_tls_is_disabled(monkeypatch):
    monkeypatch.setenv("DB_SSL_REQUIRED", "false")
    monkeypatch.setenv("DB_SSL_MODE", "verify-full")
    args = postgres_connect_args("s3cret-db-password")
    assert "sslmode" not in args


def _addrinfo(mapping):
    def resolve(host, port, *args, **kwargs):
        ips = mapping[host]
        if isinstance(ips, str):
            ips = [ips]
        rows = []
        for ip in ips:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
            rows.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return rows

    return resolve


BLOCKED_HOSTS = [
    "127.0.0.1",
    "10.0.0.5",
    "192.168.1.1",
    "169.254.169.254",
    "100.64.0.1",
    "100.100.100.200",
    "100.127.255.255",
    "224.0.0.1",
    "239.255.255.250",
    "ff02::1",
    "64:ff9b::a00:5",
    "::8.8.8.8",
    "::1",
    "fd00::1",
    "internal.example",
    "cgnat.example",
]


@pytest.mark.parametrize("host", BLOCKED_HOSTS)
def test_internal_hosts_are_blocked(host, monkeypatch):
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "")
    mapping = {name: name for name in BLOCKED_HOSTS}
    mapping["internal.example"] = "10.0.0.5"
    mapping["cgnat.example"] = "100.100.100.200"
    with patch("apps.core.db_connection.socket.getaddrinfo", side_effect=_addrinfo(mapping)):
        with pytest.raises(ValueError, match="That database host is not allowed."):
            checked_connection_host(host, 5432)


@pytest.mark.parametrize(
    ("raw", "blocked"),
    [
        ("100.100.100.200", True),
        ("100.64.0.1", True),
        ("100.127.255.255", True),
        ("8.8.8.8", False),
        ("::ffff:100.100.100.200", True),
        ("::ffff:8.8.8.8", False),
        ("127.0.0.1", True),
        ("0.0.0.0", True),
        ("224.0.0.1", True),
        ("239.255.255.250", True),
        ("ff02::1", True),
        ("64:ff9b::a00:5", True),
        ("64:ff9b::808:808", False),
        ("64:ff9b::e000:1", True),
        ("::8.8.8.8", True),
        ("::808:808", True),
        ("::ffff:224.0.0.1", True),
    ],
)
def test_only_global_addresses_are_allowed(raw, blocked):
    assert ip_is_blocked(raw) is blocked


def test_nat64_public_embed_is_allowed(monkeypatch):
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "")
    mapping = {"64:ff9b::808:808": "64:ff9b::808:808"}
    with patch("apps.core.db_connection.socket.getaddrinfo", side_effect=_addrinfo(mapping)):
        assert checked_connection_host("64:ff9b::808:808", 5432) == "64:ff9b::808:808"


def test_allowlisted_cgnat_host_uses_the_checked_address(monkeypatch):
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "db.internal")
    mapping = {"db.internal": "100.100.100.200"}
    with patch("apps.core.db_connection.socket.getaddrinfo", side_effect=_addrinfo(mapping)):
        assert checked_connection_host("db.internal", 3306) == "100.100.100.200"


def test_allowlisted_host_uses_the_checked_address(monkeypatch):
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "db.internal, 10.0.0.5")
    mapping = {"db.internal": "10.0.0.5", "10.0.0.5": "10.0.0.5"}
    with patch("apps.core.db_connection.socket.getaddrinfo", side_effect=_addrinfo(mapping)):
        assert checked_connection_host("db.internal", 5432) == "10.0.0.5"
        assert checked_connection_host("10.0.0.5", 3306) == "10.0.0.5"


def test_mixed_resolution_is_blocked_unless_allowlisted(monkeypatch):
    mapping = {"db.example.com": ["8.8.8.8", "10.0.0.5"]}
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "")
    with patch("apps.core.db_connection.socket.getaddrinfo", side_effect=_addrinfo(mapping)):
        with pytest.raises(ValueError, match="not allowed"):
            checked_connection_host("db.example.com", 5432)
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "db.example.com")
    with patch("apps.core.db_connection.socket.getaddrinfo", side_effect=_addrinfo(mapping)):
        assert checked_connection_host("db.example.com", 5432) == "8.8.8.8"


def test_server_workspace_stores_the_checked_ip_without_a_password(monkeypatch):
    password = "p@ss word"
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "")
    monkeypatch.setenv("DB_SSL_REQUIRED", "true")
    monkeypatch.delenv("DB_SSL_MODE", raising=False)
    monkeypatch.setattr(
        "apps.core.db_connection.socket.getaddrinfo",
        _addrinfo({"db.example.com": "8.8.8.8"}),
    )
    monkeypatch.setattr("apps.core.workspaces.get_schema_snapshot", lambda *args, **kwargs: "Table: events")

    workspace = create_server_workspace(
        "Reporting",
        engine="postgresql",
        host="db.example.com",
        port=5432,
        database="reporting",
        username="readonly",
        password=password,
    )
    assert workspace.database_uri == "postgresql+psycopg://readonly@8.8.8.8:5432/reporting"
    assert "?" not in workspace.database_uri
    assert password not in workspace.database_uri
    assert password not in repr(workspace)
    assert workspace.connect_args["sslmode"] == "require"
    assert str(workspace.connect_args["password"]) == "***"

    mysql = create_server_workspace(
        "Reporting",
        engine="mysql",
        host="db.example.com",
        port=3306,
        database="reporting",
        username="readonly",
        password=password,
    )
    assert mysql.database_uri == "mysql+pymysql://readonly@8.8.8.8:3306/reporting"
    assert mysql.connect_args["local_infile"] is False
    assert password not in repr(mysql)


def test_probe_errors_hide_driver_text(monkeypatch, caplog):
    password = "s3cret-db-password"

    def explode(*_args, **_kwargs):
        raise OperationalError("CONNECT", {}, Exception(f"DRIVER_TOKEN password={password} local_infile=1"))

    monkeypatch.setenv("ALLOWED_DB_HOSTS", "")
    monkeypatch.setattr(
        "apps.core.db_connection.socket.getaddrinfo",
        _addrinfo({"db.example.com": "8.8.8.8"}),
    )
    monkeypatch.setattr("apps.core.workspaces.get_schema_snapshot", explode)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(DatabaseConnectionError, match="^Could not connect to the database$") as caught:
            create_server_workspace(
                "Reporting",
                engine="postgresql",
                host="db.example.com",
                port=5432,
                database="reporting",
                username="readonly",
                password=password,
            )
    assert password not in str(caught.value)
    assert "DRIVER_TOKEN" not in str(caught.value)
    assert "local_infile" not in str(caught.value)
    assert password not in caplog.text
    assert "DRIVER_TOKEN" in caplog.text


def test_executor_postgres_select_passes_the_guardrail():
    with patch("apps.core.executor.create_engine"):
        executor = ReadOnlyExecutor(
            "postgresql+psycopg://readonly@8.8.8.8:5432/reporting",
            dialect="postgresql",
        )
    guarded = executor.prepare("SELECT id FROM events")
    assert executor.guardrails.dialect == "postgres"
    assert "LIMIT 500" in guarded.sql
    assert "events" in guarded.sql


def test_executor_forces_mysql_local_infile_off():
    with patch("apps.core.executor.create_engine") as create_engine:
        ReadOnlyExecutor(
            "mysql+pymysql://readonly@8.8.8.8:3306/reporting",
            dialect="mysql",
            connect_args={"local_infile": True, "password": SecretValue("s3cret-db-password")},
        )
    kwargs = create_engine.call_args.kwargs
    assert kwargs["connect_args"]["local_infile"] is False
    assert kwargs["connect_args"]["password"] == "s3cret-db-password"
    assert "s3cret-db-password" not in create_engine.call_args.args[0]
