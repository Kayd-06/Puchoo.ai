"""Signup, login, logout, and the current-user endpoint."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import emailer
from backend.database import get_db
from backend.emailer import EmailDeliveryError
from backend.models import AuthSession, InstituteInvite, LoginCode, PasswordResetCode, User
from backend.rate_limit import limiter
from backend.schemas import (
    AuthResponse,
    LoginRequest,
    OtpChallengeResponse,
    InstituteInviteResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    ResendOtpRequest,
    SignupRequest,
    UserResponse,
    VerifyLoginRequest,
)
from backend.security import (
    GENERIC_SIGNUP_ERROR,
    INVALID_LOGIN_ERROR,
    RATE_LIMIT_ERROR,
    SESSION_TTL,
    as_utc,
    clear_session_cookie,
    client_ip,
    enforce_csrf,
    hash_password,
    hash_token,
    new_session_token,
    set_session_cookie,
    tokens_match,
    utcnow,
    verify_password,
    verify_password_for_missing_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])
OTP_TTL = timedelta(minutes=10)
INVALID_CODE = "That code is invalid or has expired."
EMAIL_FAILED = "We could not send the verification email. Try again in a moment."


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def _rate_limit(action: str, request: Request, email: str) -> None:
    allowed = limiter.allow(
        [
            f"{action}:ip:{client_ip(request)}",
            f"{action}:email:{email}",
        ]
    )
    if not allowed:
        raise HTTPException(status_code=429, detail=RATE_LIMIT_ERROR, headers={"Retry-After": "900"})


def _issue_session(db: Session, user: User, response: Response) -> None:
    raw_token = new_session_token()
    now = utcnow()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            created_at=now,
            expires_at=now + SESSION_TTL,
        )
    )
    db.commit()
    set_session_cookie(response, raw_token)


def _active_session(db: Session, raw_token: str | None) -> AuthSession | None:
    if not raw_token:
        return None
    record = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(raw_token)))
    if record is None or record.revoked_at is not None:
        return None
    if as_utc(record.expires_at) <= utcnow():
        return None
    return record


def current_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    from backend.config import settings

    record = _active_session(db, request.cookies.get(settings.session_cookie_name))
    if record is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    now = utcnow()
    record.expires_at = now + timedelta(days=7)
    db.commit()
    set_session_cookie(response, request.cookies[settings.session_cookie_name])
    return record.user


@router.get("/csrf", status_code=204)
def issue_csrf() -> Response:
    """The CSRF cookie middleware attaches the double-submit cookie."""

    return Response(status_code=204)


@router.post("/signup", response_model=OtpChallengeResponse, status_code=202)
def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> OtpChallengeResponse:
    enforce_csrf(request)
    _rate_limit("signup", request, body.email)
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status_code=400, detail=GENERIC_SIGNUP_ERROR)

    owner = None
    if body.institute_code:
        invite = db.scalar(select(InstituteInvite).where(InstituteInvite.code_hash == hash_token(body.institute_code), InstituteInvite.revoked_at.is_(None)))
        if invite is None:
            raise HTTPException(status_code=400, detail="That institute invite code is invalid.")
        owner = db.get(User, invite.owner_user_id)
        if owner is None:
            raise HTTPException(status_code=400, detail="That institute invite code is invalid.")
    user = User(
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        workspace_type="institute" if owner else body.workspace_type,
        institute_name=owner.institute_name if owner else body.institute_name,
        institute_owner_id=owner.id if owner else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=GENERIC_SIGNUP_ERROR) from None
    db.refresh(user)
    try:
        _send_login_code(db, user)
    except HTTPException:
        # Do not leave an unreachable account behind when delivery is unavailable.
        db.delete(user)
        db.commit()
        raise
    return OtpChallengeResponse(email=user.email)


@router.post("/institute/invite", response_model=InstituteInviteResponse)
def create_institute_invite(request: Request, response: Response, db: Session = Depends(get_db)) -> InstituteInviteResponse:
    enforce_csrf(request)
    user = current_user(request, response, db)
    if user.workspace_type != "institute" or user.institute_owner_id:
        raise HTTPException(status_code=403, detail="Only the institute owner can create invite codes.")
    now = utcnow()
    for invite in db.scalars(select(InstituteInvite).where(InstituteInvite.owner_user_id == user.id, InstituteInvite.revoked_at.is_(None))).all():
        invite.revoked_at = now
    code = f"PUCHOO-{secrets.token_urlsafe(7).upper()}"
    db.add(InstituteInvite(owner_user_id=user.id, code_hash=hash_token(code)))
    db.commit()
    return InstituteInviteResponse(code=code, institute_name=user.institute_name or "Institute workspace")


def _send_login_code(db: Session, user: User) -> None:
    now = utcnow()
    pending = db.scalars(
        select(LoginCode).where(LoginCode.user_id == user.id, LoginCode.consumed_at.is_(None))
    ).all()
    for row in pending:
        row.consumed_at = now
    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    record = LoginCode(
        user_id=user.id,
        code_hash=hash_token(raw_code),
        attempts=0,
        created_at=now,
        expires_at=now + OTP_TTL,
    )
    db.add(record)
    db.commit()
    try:
        emailer.send_otp_email(user.email, raw_code)
    except EmailDeliveryError:
        record.consumed_at = utcnow()
        db.commit()
        raise HTTPException(status_code=503, detail=EMAIL_FAILED) from None


@router.post("/login", response_model=OtpChallengeResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> OtpChallengeResponse:
    enforce_csrf(request)
    _rate_limit("login", request, str(body.email))
    user = db.scalar(select(User).where(User.email == str(body.email)))
    if user is None:
        verify_password_for_missing_user(body.password)
        raise HTTPException(status_code=401, detail=INVALID_LOGIN_ERROR)
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail=INVALID_LOGIN_ERROR)
    _send_login_code(db, user)
    return OtpChallengeResponse(email=user.email)


@router.post("/login/resend", response_model=OtpChallengeResponse)
def resend_login_code(
    body: ResendOtpRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> OtpChallengeResponse:
    """Replace a pending code without requiring the user to re-enter a password."""

    enforce_csrf(request)
    _rate_limit("resend", request, str(body.email))
    user = db.scalar(select(User).where(User.email == str(body.email)))
    if user is not None:
        _send_login_code(db, user)
    # Keep this response uniform so the endpoint does not disclose accounts.
    return OtpChallengeResponse(email=str(body.email))


@router.post("/password/forgot", response_model=OtpChallengeResponse)
def forgot_password(body: PasswordForgotRequest, request: Request, db: Session = Depends(get_db)) -> OtpChallengeResponse:
    enforce_csrf(request)
    _rate_limit("password-reset", request, str(body.email))
    user = db.scalar(select(User).where(User.email == str(body.email)))
    if user is not None:
        now = utcnow()
        for row in db.scalars(select(PasswordResetCode).where(PasswordResetCode.user_id == user.id, PasswordResetCode.consumed_at.is_(None))).all():
            row.consumed_at = now
        code = f"{secrets.randbelow(1_000_000):06d}"
        db.add(PasswordResetCode(user_id=user.id, code_hash=hash_token(code), attempts=0, expires_at=now + OTP_TTL))
        db.commit()
        try:
            emailer.send_otp_email(user.email, code)
        except EmailDeliveryError:
            raise HTTPException(status_code=503, detail=EMAIL_FAILED) from None
    return OtpChallengeResponse(email=str(body.email))


@router.post("/password/reset")
def reset_password(body: PasswordResetRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    enforce_csrf(request)
    _rate_limit("password-reset-verify", request, str(body.email))
    user = db.scalar(select(User).where(User.email == str(body.email)))
    record = db.scalar(select(PasswordResetCode).where(PasswordResetCode.user_id == user.id, PasswordResetCode.consumed_at.is_(None)).order_by(PasswordResetCode.expires_at.desc())) if user else None
    if record is None or record.attempts >= 5 or as_utc(record.expires_at) <= utcnow() or not tokens_match(record.code_hash, hash_token(body.code)):
        if record is not None:
            record.attempts += 1
            db.commit()
        raise HTTPException(status_code=401, detail=INVALID_CODE)
    record.consumed_at = utcnow()
    user.password_hash = hash_password(body.password)
    db.commit()
    return {"ok": True}


@router.post("/login/verify", response_model=AuthResponse)
def verify_login(
    body: VerifyLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    enforce_csrf(request)
    _rate_limit("verify", request, str(body.email))
    user = db.scalar(select(User).where(User.email == str(body.email)))
    record = None
    if user is not None:
        record = db.scalar(
            select(LoginCode)
            .where(LoginCode.user_id == user.id, LoginCode.consumed_at.is_(None))
            .order_by(LoginCode.created_at.desc())
        )
    now = utcnow()
    if record is None or record.attempts >= 5 or as_utc(record.expires_at) <= now:
        raise HTTPException(status_code=401, detail=INVALID_CODE)
    if not tokens_match(record.code_hash, hash_token(body.code)):
        record.attempts += 1
        if record.attempts >= 5:
            record.consumed_at = now
        db.commit()
        raise HTTPException(status_code=401, detail=INVALID_CODE)
    record.consumed_at = now
    db.commit()
    _issue_session(db, user, response)
    return AuthResponse(user=_user_response(user))


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    enforce_csrf(request)
    from backend.config import settings

    record = _active_session(db, request.cookies.get(settings.session_cookie_name))
    if record is not None and record.revoked_at is None:
        record.revoked_at = utcnow()
        db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
    return _user_response(user)
