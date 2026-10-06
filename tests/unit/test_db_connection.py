"""Connection fields cannot change driver settings or reach internal hosts."""

from __future__ import annotations

import logging
import socket
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from apps.core.db_connection import (
    DatabaseConnectionError,
    SecretValue,
    ServerConnection,
    build_server_url,
    checked_connection_host,
    materialize_connect_args,
    mysql_connect_args,
    postgres_connect_args,
    render_password_free,
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
    args = mysql_connect_args("s3cret-db-password")
    assert args["local_infile"] is False
    assert args["ssl"] == {}
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


def test_postgres_connect_args_are_read_only(monkeypatch):
    monkeypatch.delenv("DB_SSL_REQUIRED", raising=False)
    args = postgres_connect_args("s3cret-db-password")
    assert args["sslmode"] == "require"
    assert args["connect_timeout"] == 10
    assert "default_transaction_read_only=on" in args["options"]
    assert "statement_timeout=30000" in args["options"]
    assert str(args["password"]) == "***"


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
    "::1",
    "fd00::1",
    "internal.example",
]


@pytest.mark.parametrize("host", BLOCKED_HOSTS)
def test_internal_hosts_are_blocked(host, monkeypatch):
    monkeypatch.setenv("ALLOWED_DB_HOSTS", "")
    mapping = {name: name for name in BLOCKED_HOSTS}
    mapping["internal.example"] = "10.0.0.5"
    with patch("apps.core.db_connection.socket.getaddrinfo", side_effect=_addrinfo(mapping)):
        with pytest.raises(ValueError, match="That database host is not allowed."):
            checked_connection_host(host, 5432)


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
