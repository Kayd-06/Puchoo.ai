"""Password hashing, session tokens, and CSRF comparison.

Raw passwords and session tokens are never written to logs or to the database.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, Response

from backend.config import settings

_password_hasher = PasswordHasher()
_DUMMY_PASSWORD_HASH = _password_hasher.hash("dummy-password-not-used")
SESSION_TTL = timedelta(days=settings.session_days)
GENERIC_SIGNUP_ERROR = "Unable to create an account with those details."
INVALID_LOGIN_ERROR = "Invalid email or password"
CSRF_ERROR = "CSRF token missing or invalid"
RATE_LIMIT_ERROR = "Too many attempts. Try again in 15 minutes."


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def verify_password_for_missing_user(password: str) -> None:
    """Spend the same hash verification time when the email is unknown."""

    verify_password(password, _DUMMY_PASSWORD_HASH)


def password_is_valid(password: str) -> bool:
    if len(password) < 10 or len(password) > 128:
        return False
    has_letter = any(character.isalpha() for character in password)
    has_number = any(character.isdigit() for character in password)
    return has_letter and has_number


def new_session_token() -> str:
    """256-bit random token. Only its SHA-256 hash is stored."""

    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(left: str | None, right: str | None) -> bool:
    if not left or not right or len(left) != len(right):
        return False
    return secrets.compare_digest(left, right)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_csrf(request: Request) -> None:
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get(settings.csrf_header_name)
    if not tokens_match(cookie, header):
        raise HTTPException(status_code=403, detail=CSRF_ERROR)


def _cookie_kwargs(http_only: bool) -> dict:
    return {
        "httponly": http_only,
        "samesite": "lax",
        "secure": settings.cookie_secure,
        "path": "/",
        "max_age": int(SESSION_TTL.total_seconds()),
    }


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(settings.session_cookie_name, raw_token, **_cookie_kwargs(http_only=True))


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        samesite="lax",
        secure=settings.cookie_secure,
        httponly=True,
    )


def set_csrf_cookie(response: Response, token: str | None = None) -> str:
    value = token or new_csrf_token()
    response.set_cookie(settings.csrf_cookie_name, value, **_cookie_kwargs(http_only=False))
    return value
