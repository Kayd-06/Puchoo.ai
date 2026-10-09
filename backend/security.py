"""Password hashing, signed JWT sessions, and CSRF comparison.

Raw passwords and session tokens are never written to logs or to the database.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
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
    except (VerifyMismatchError, InvalidHash):
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


def new_session_token(user_id: str, session_id: str, expires_at: datetime) -> str:
    """Create a signed, short-lived JWT for one server-side session record.

    The full token remains only in the HttpOnly browser cookie.  Its hash is
    retained server-side so logout, rotation, and emergency revocation remain
    effective even though the JWT itself is statelessly verifiable.
    """

    now = utcnow()
    return jwt.encode(
        {
            "sub": user_id,
            "jti": session_id,
            "iat": now,
            "exp": as_utc(expires_at),
            "iss": settings.jwt_issuer,
        },
        settings.session_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_session_token(token: str) -> dict[str, str] | None:
    """Validate the signature, expiry and issuer without exposing decode errors."""

    try:
        payload = jwt.decode(
            token,
            settings.session_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "jti", "exp", "iat", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    if not isinstance(payload.get("sub"), str) or not isinstance(payload.get("jti"), str):
        return None
    return {"sub": payload["sub"], "jti": payload["jti"]}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_otp(code: str) -> str:
    """HMAC-SHA256 of a one-time code. The raw code is never stored."""

    return hmac.new(
        settings.otp_secret.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def otp_matches(code: str, code_hash: str) -> bool:
    if not code_hash or len(code_hash) != 64:
        return False
    return hmac.compare_digest(hash_otp(code), code_hash)


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


LOGIN_CHALLENGE_MAX_AGE = 300


def set_login_challenge_cookie(response: Response, challenge_id: str) -> None:
    """Hand the password-proven challenge id to the browser only as a cookie."""

    response.set_cookie(
        settings.login_challenge_cookie_name,
        challenge_id,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
        max_age=LOGIN_CHALLENGE_MAX_AGE,
    )


def clear_login_challenge_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.login_challenge_cookie_name,
        path="/",
        samesite="strict",
        secure=settings.cookie_secure,
        httponly=True,
    )
