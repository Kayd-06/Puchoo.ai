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

import certifi
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine

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
HOST_NOT_ALLOWED_ERROR = "That database host is not allowed."
HOST_UNRESOLVED_ERROR = "Could not resolve the database host."
# These stay off the HTTP response. Callers return GENERIC_CONNECTION_ERROR instead.
GENERIC_HOST_ERRORS = frozenset({HOST_NOT_ALLOWED_ERROR, HOST_UNRESOLVED_ERROR})
POSTGRES_SSL_MODES = frozenset({"require", "verify-ca", "verify-full"})
# Deprecated IPv4-compatible form (::a.b.c.d). Python can report these as global.
_IPV4_COMPATIBLE_NETWORK = ipaddress.IPv6Network("::/96")
# Well-known NAT64 prefix. The last 32 bits are the embedded IPv4 address.
_NAT64_NETWORK = ipaddress.IPv6Network("64:ff9b::/96")


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
    required = value.strip().lower() not in {"0", "false", "no", "off"}
    if not required and os.getenv("ENVIRONMENT", "development").strip().lower() == "production":
        raise ValueError("Database TLS is required in production.")
    return required


def allowed_db_hosts() -> set[str]:
    raw = os.getenv("ALLOWED_DB_HOSTS", "")
    return {item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip()}


def _address_is_blocked(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when an address must not be used as a database endpoint.

    Multicast is checked on its own: Python reports 224.0.0.0/4 and ff00::/8
    as global. CGNAT (100.64.0.0/10) is not global even though it is not private.
    """

    return (not address.is_global) or address.is_multicast


def ip_is_blocked(raw: str) -> bool:
    """Reject addresses that are not safe to open a database connection to."""

    address: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(raw.split("%", 1)[0])
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    if isinstance(address, ipaddress.IPv6Address):
        if address in _IPV4_COMPATIBLE_NETWORK:
            return True
        if address in _NAT64_NETWORK:
            embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
            return _address_is_blocked(embedded)
    return _address_is_blocked(address)


def resolved_ips(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(HOST_UNRESOLVED_ERROR) from exc
    found: list[str] = []
    for info in infos:
        ip = str(info[4][0]).split("%", 1)[0]
        if ip not in found:
            found.append(ip)
    if not found:
        raise ValueError(HOST_UNRESOLVED_ERROR)
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
        raise ValueError(HOST_NOT_ALLOWED_ERROR)
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


def mysql_ca_file() -> str:
    """CA bundle for MySQL. DB_SSL_CA overrides certifi's Mozilla bundle."""

    configured = os.getenv("DB_SSL_CA", "").strip()
    return configured or certifi.where()


def mysql_connect_args(password: str) -> dict:
    args: dict = {
        "password": SecretValue(password),
        "local_infile": False,
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
    }
    if db_ssl_required():
        # An empty ssl dict only prefers TLS and can fall back to plaintext.
        # ssl_verify_cert makes PyMySQL require a valid certificate. The same
        # path is also passed as ssl_ca: when that flag is set, PyMySQL rebuilds
        # its SSL dict from ssl_ca and would otherwise drop the bundle.
        ca_file = mysql_ca_file()
        args["ssl"] = {"ca": ca_file}
        args["ssl_ca"] = ca_file
        args["ssl_verify_cert"] = True
        args["ssl_verify_identity"] = True
        args["ssl_disabled"] = False
    else:
        args["ssl_disabled"] = True
    return args


def db_ssl_mode() -> str:
    """Legacy require/verify-ca settings are upgraded, never used to weaken TLS."""

    mode = os.getenv("DB_SSL_MODE", "verify-full").strip().lower() or "verify-full"
    if mode not in POSTGRES_SSL_MODES:
        raise ValueError("DB_SSL_MODE must be require, verify-ca or verify-full; all use verify-full.")
    return "verify-full"


def validate_db_ssl_mode() -> None:
    """Validate policy at startup; production cannot opt out of database TLS."""

    db_ssl_required()
    db_ssl_mode()


def postgres_connect_args(password: str) -> dict:
    args: dict = {
        "password": SecretValue(password),
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "options": "-c default_transaction_read_only=on -c statement_timeout=" + str(STATEMENT_TIMEOUT_MS),
    }
    if db_ssl_required():
        args["sslmode"] = db_ssl_mode()
        args["sslrootcert"] = os.getenv("DB_SSL_ROOT_CERT", "").strip() or certifi.where()
    else:
        # Explicit development-only opt-out; do not inherit libpq's prefer mode.
        args["sslmode"] = "disable"
    return args


def connect_args_for(dialect: str, password: str, *, pinned_ip: str | None = None) -> dict:
    if dialect == "mysql":
        args = mysql_connect_args(password)
        if pinned_ip is not None:
            args["_pinned_ip"] = pinned_ip
        return args
    if dialect == "postgresql":
        args = postgres_connect_args(password)
        if pinned_ip is not None:
            args["hostaddr"] = pinned_ip
        return args
    raise ValueError("Dialect must be postgresql or mysql.")


def create_database_engine(database_uri: str, *, connect_args: Mapping | None = None) -> Engine:
    """Keep the URL's original TLS identity separate from the checked endpoint.

    libpq supports host (identity) plus hostaddr (network route). PyMySQL exposes
    Connection.connect(sock=...), so supply a numeric-address socket while its
    host/ssl_verify_identity still control SNI and hostname verification. The
    SQLAlchemy do_connect hook applies to every new pooled connection.
    """

    args = materialize_connect_args(connect_args)
    if database_uri.startswith("mysql"):
        args["local_infile"] = False
    pinned_ip = args.pop("_pinned_ip", None)
    if pinned_ip is not None:
        address = ipaddress.ip_address(pinned_ip)  # Never permit a second hostname resolution.
        if not database_uri.startswith("mysql+pymysql:"):
            raise ValueError("Pinned socket is only supported by PyMySQL.")
    engine = create_engine(database_uri, connect_args=args)
    if pinned_ip is not None:
        @event.listens_for(engine, "do_connect")
        def connect_pinned(dialect, _record, cargs, cparams):
            connection = dialect.loaded_dbapi.connect(*cargs, **cparams, defer_connect=True)
            family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            try:
                sock.settimeout(cparams.get("connect_timeout", CONNECT_TIMEOUT_SECONDS))
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                sock.connect((str(address), cparams.get("port", 3306)))
                connection.connect(sock=sock)
                return connection
            except BaseException:
                sock.close()
                raise
    return engine


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
