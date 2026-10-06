"""Strict database connection settings.

Connection fields are validated before a URL exists. The URL is built with
SQLAlchemy's URL.create and never includes a query string. The password is
passed to the driver separately so it is not kept in the URL string.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from typing import Mapping
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.engine import URL

HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    r"(?:\.(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?))*$"
)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,64}$")
DRIVERS = {
    "postgresql": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
}
CONNECT_TIMEOUT_SECONDS = 10
STATEMENT_TIMEOUT_MS = 30_000
GENERIC_CONNECTION_ERROR = "Could not connect to the database"


class DatabaseConnectionError(RuntimeError):
    """A connection failed. The message is safe to show to a client."""


class SecretValue:
    """A password that stays out of repr, str, and JSON dumps."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretValue('***')"

    def __str__(self) -> str:
        return "***"

    def __deepcopy__(self, memo: dict) -> SecretValue:
        cloned = SecretValue(self._value)
        memo[id(self)] = cloned
        return cloned


class ServerConnection(BaseModel):
    """Fields a workspace may use to open PostgreSQL or MySQL."""

    model_config = ConfigDict(extra="ignore")

    dialect: str = Field(pattern="^(postgresql|mysql)$")
    host: str
    port: int
    database: str
    username: str
    password: str

    @field_validator("dialect")
    @classmethod
    def known_dialect(cls, value: str) -> str:
        if value not in DRIVERS:
            raise ValueError("Dialect must be postgresql or mysql.")
        return value

    @field_validator("host")
    @classmethod
    def host_is_hostname_or_ip(cls, value: str) -> str:
        if not isinstance(value, str) or value != value.strip() or not value:
            raise ValueError("Host must be a hostname or IP address without whitespace.")
        if len(value) > 253:
            raise ValueError("Host must be at most 253 characters.")
        if re.search(r"[/?#@%\s]", value):
            raise ValueError("Host cannot contain / ? # @, whitespace, or encoded characters.")
        if _is_ip_address(value):
            return value
        if ":" in value or not HOSTNAME_RE.fullmatch(value):
            raise ValueError("Host must be a hostname or IP address.")
        return value

    @field_validator("port", mode="before")
    @classmethod
    def port_is_integer(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Port must be an integer from 1 to 65535.")
        return value

    @field_validator("port")
    @classmethod
    def port_in_range(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("Port must be an integer from 1 to 65535.")
        return value

    @field_validator("database", "username")
    @classmethod
    def identifier(cls, value: str) -> str:
        if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
            raise ValueError("Use 1 to 64 letters, numbers, dots, underscores, or hyphens.")
        return value

    @field_validator("password")
    @classmethod
    def password_length(cls, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("Password is required.")
        if len(value) > 256 or "\x00" in value:
            raise ValueError("Password must be at most 256 characters.")
        return value


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def db_ssl_required() -> bool:
    """TLS stays on unless this server-side flag explicitly turns it off."""

    value = os.getenv("DB_SSL_REQUIRED")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


def allowed_db_hosts() -> set[str]:
    raw = os.getenv("ALLOWED_DB_HOSTS", "")
    return {item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip()}


def ip_is_blocked(raw: str) -> bool:
    """Reject loopback, private, link-local, multicast, reserved, and unspecified addresses."""

    address: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(raw.split("%", 1)[0])
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def resolved_ips(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Could not resolve the database host.") from exc
    found: list[str] = []
    for info in infos:
        ip = str(info[4][0]).split("%", 1)[0]
        if ip not in found:
            found.append(ip)
    if not found:
        raise ValueError("Could not resolve the database host.")
    return found


def host_is_allowlisted(host: str, ips: list[str]) -> bool:
    allowed = allowed_db_hosts()
    if not allowed:
        return False
    candidates = {host.strip().lower().rstrip(".")}
    candidates.update(ip.lower() for ip in ips)
    return bool(candidates & allowed)


def checked_connection_host(host: str, port: int) -> str:
    """Return one resolved IP that was checked. Refuse the name if any address is internal."""

    ips = resolved_ips(host, port)
    blocked = [ip for ip in ips if ip_is_blocked(ip)]
    if blocked and not host_is_allowlisted(host, ips):
        raise ValueError("That database host is not allowed.")
    for ip in ips:
        if not ip_is_blocked(ip):
            return ip
    return ips[0]


def build_server_url(
    *,
    dialect: str,
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
) -> URL:
    """Build a connection URL. Callers must not stringify this object."""

    url = URL.create(
        drivername=DRIVERS[dialect],
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    if url.query:
        raise ValueError("Database connection URLs cannot include query parameters.")
    return url


def password_free_url(url: URL) -> URL:
    """Drop the password. URL.set ignores None, so replace the field directly."""

    return url._replace(password=None)


def render_password_free(url: URL) -> str:
    safe = password_free_url(url)
    rendered = safe.render_as_string(hide_password=False)
    if safe.password is not None or "?" in rendered or safe.query:
        raise RuntimeError("Refusing to store a database URL that contains a password or query string.")
    return rendered


def mysql_connect_args(password: str) -> dict:
    args: dict = {
        "password": SecretValue(password),
        "local_infile": False,
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
    }
    if db_ssl_required():
        args["ssl"] = {}
        args["ssl_disabled"] = False
    else:
        args["ssl_disabled"] = True
    return args


def postgres_connect_args(password: str) -> dict:
    args: dict = {
        "password": SecretValue(password),
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "options": "-c default_transaction_read_only=on -c statement_timeout=" + str(STATEMENT_TIMEOUT_MS),
    }
    if db_ssl_required():
        args["sslmode"] = "require"
    return args


def connect_args_for(dialect: str, password: str) -> dict:
    if dialect == "mysql":
        return mysql_connect_args(password)
    if dialect == "postgresql":
        return postgres_connect_args(password)
    raise ValueError("Dialect must be postgresql or mysql.")


def materialize_connect_args(connect_args: Mapping | None) -> dict:
    """Copy driver arguments, revealing a masked password only for the driver."""

    if not connect_args:
        return {}
    ready: dict = {}
    for key, value in connect_args.items():
        if isinstance(value, SecretValue):
            ready[key] = value.reveal()
        else:
            ready[key] = value
    if "local_infile" in ready:
        ready["local_infile"] = False
    return ready


def redact_secret(text: str, secret: str) -> str:
    if not text or not secret:
        return text
    redacted = text.replace(secret, "***")
    encoded = quote_plus(secret)
    if encoded and encoded != secret:
        redacted = redacted.replace(encoded, "***")
    return redacted
