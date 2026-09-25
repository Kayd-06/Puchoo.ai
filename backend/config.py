"""Runtime settings. Secrets come from the environment, never from the client."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

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


@dataclass
class Settings:
    database_url: str
    frontend_origins: list[str]
    cookie_secure: bool
    environment: str
    session_cookie_name: str = "puchoo_session"
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
    session_days: int = 7
    session_secret: str = "dev-secret-key-do-not-use-in-prod"
    smtp_server: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False


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
        session_secret=os.getenv("SESSION_SECRET", "dev-secret-key-do-not-use-in-prod"),
        smtp_server=os.getenv("SMTP_SERVER"),
        smtp_port=parsed_smtp_port,
        smtp_username=os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_from=os.getenv("SMTP_FROM"),
        smtp_use_tls=_as_bool(os.getenv("SMTP_USE_TLS"), default=True),
        smtp_use_ssl=_as_bool(os.getenv("SMTP_USE_SSL"), default=False),
    )


settings = load_settings()
