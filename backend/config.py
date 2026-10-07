"""Runtime settings. Secrets come from the environment, never from the client."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from apps.core.db_connection import validate_db_ssl_mode

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DATABASE_PATH = BACKEND_DIR / "puchoo_auth.db"


def _load_env_files() -> None:
    """Fill missing environment variables from the repo .env, then backend/.env."""

    merged: dict[str, str] = {}
    for path in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        for key, value in dotenv_values(path).items():
            if value is not None:
                merged[key] = value
    for key, value in merged.items():
        os.environ.setdefault(key, value)


_load_env_files()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    """Read a bounded positive integer without making a bad deploy config fatal."""

    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


DEFAULT_SESSION_SECRET = "dev-secret-key-do-not-use-in-prod"
DEFAULT_OTP_SECRET = "dev-otp-secret-do-not-use-in-prod"
# Values that ship with the repo. Production must replace both secrets.
UNSAFE_SECRET_VALUES = frozenset(
    {
        "",
        DEFAULT_SESSION_SECRET,
        DEFAULT_OTP_SECRET,
        "replace-with-a-long-random-string",
        "changeme",
        "change-me",
    }
)


def secret_is_unsafe(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in UNSAFE_SECRET_VALUES


def ensure_production_secrets(environment: str, session_secret: str | None, otp_secret: str | None) -> None:
    """Stop the process when a production deploy is still using placeholder secrets."""

    if environment.strip().lower() != "production":
        return
    missing: list[str] = []
    if secret_is_unsafe(session_secret):
        missing.append("SESSION_SECRET")
    if secret_is_unsafe(otp_secret):
        missing.append("OTP_SECRET")
    if missing:
        names = " and ".join(missing)
        raise RuntimeError(
            f"Refusing to start: {names} must be set to a non-default value when ENVIRONMENT=production."
        )


@dataclass
class Settings:
    database_url: str
    frontend_origins: list[str]
    cookie_secure: bool
    environment: str
    session_cookie_name: str = "puchoo_session"
    login_challenge_cookie_name: str = "puchoo_login_challenge"
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
    session_days: int = 7
    session_secret: str = DEFAULT_SESSION_SECRET
    otp_secret: str = DEFAULT_OTP_SECRET
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "puchoo.ai"
    smtp_server: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_from_name: str = "Puchoo.si no-reply"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    upload_max_bytes: int = 25 * 1024 * 1024
    upload_max_files: int = 10
    auth_rate_limit: int = 5
    auth_rate_window_seconds: int = 15 * 60
    auth_backoff_base_seconds: int = 60
    auth_backoff_max_seconds: int = 15 * 60
    public_rate_limit: int = 120
    public_rate_window_seconds: int = 60
    authenticated_rate_limit: int = 300
    authenticated_rate_window_seconds: int = 60
    connection_rate_limit: int = 5
    connection_rate_window_seconds: int = 15 * 60


def load_settings() -> Settings:
    origins = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    database_url = os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    smtp_port = os.getenv("SMTP_PORT")
    try:
        parsed_smtp_port = int(smtp_port) if smtp_port else None
    except ValueError:
        parsed_smtp_port = None
    return Settings(
        database_url=database_url,
        frontend_origins=[item.strip() for item in origins.split(",") if item.strip()],
        cookie_secure=_as_bool(os.getenv("COOKIE_SECURE"), default=False),
        environment=os.getenv("ENVIRONMENT", "development"),
        session_secret=os.getenv("SESSION_SECRET", DEFAULT_SESSION_SECRET),
        otp_secret=os.getenv("OTP_SECRET", DEFAULT_OTP_SECRET),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_issuer=os.getenv("JWT_ISSUER", "puchoo.ai"),
        smtp_server=os.getenv("SMTP_SERVER"),
        smtp_port=parsed_smtp_port,
        smtp_username=os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_from=os.getenv("SMTP_FROM"),
        smtp_from_name=os.getenv("SMTP_FROM_NAME", "Puchoo.si no-reply").strip() or "Puchoo.si no-reply",
        smtp_use_tls=_as_bool(os.getenv("SMTP_USE_TLS"), default=True),
        smtp_use_ssl=_as_bool(os.getenv("SMTP_USE_SSL"), default=False),
        upload_max_bytes=_positive_int("UPLOAD_MAX_BYTES", 25 * 1024 * 1024),
        upload_max_files=_positive_int("UPLOAD_MAX_FILES", 10),
        auth_rate_limit=_positive_int("AUTH_RATE_LIMIT", 5),
        auth_rate_window_seconds=_positive_int("AUTH_RATE_WINDOW_SECONDS", 15 * 60),
        auth_backoff_base_seconds=_positive_int("AUTH_BACKOFF_BASE_SECONDS", 60),
        auth_backoff_max_seconds=_positive_int("AUTH_BACKOFF_MAX_SECONDS", 15 * 60),
        public_rate_limit=_positive_int("PUBLIC_RATE_LIMIT", 120),
        public_rate_window_seconds=_positive_int("PUBLIC_RATE_WINDOW_SECONDS", 60),
        authenticated_rate_limit=_positive_int("AUTHENTICATED_RATE_LIMIT", 300),
        authenticated_rate_window_seconds=_positive_int("AUTHENTICATED_RATE_WINDOW_SECONDS", 60),
        connection_rate_limit=_positive_int("CONNECTION_RATE_LIMIT", 5),
        connection_rate_window_seconds=_positive_int("CONNECTION_RATE_WINDOW_SECONDS", 15 * 60),
    )


settings = load_settings()
ensure_production_secrets(settings.environment, settings.session_secret, settings.otp_secret)
validate_db_ssl_mode()
