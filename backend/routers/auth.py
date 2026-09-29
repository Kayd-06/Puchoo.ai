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
from backend.models import AuthSession, EmailChangeCode, InstituteInvite, LoginCode, PasswordResetCode, User
from backend.notifications import create_notification
from backend.rate_limit import limiter
from backend.schemas import (
    AuthResponse,
    EmailChangeRequest,
    EmailChangeVerifyRequest,
    LoginRequest,
    OtpChallengeResponse,
    InstituteInviteResponse,
    WorkspaceInviteRequest,
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
    decode_session_token,
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
SESSION_ROTATION_GRACE = timedelta(minutes=2)
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
    now = utcnow()
    record = AuthSession(
        user_id=user.id,
        # Set after flush assigns the session id used as the JWT jti claim.
        token_hash="pending",
        created_at=now,
        expires_at=now + SESSION_TTL,
    )
    db.add(record)
    db.flush()
    raw_token = new_session_token(user.id, record.id, record.expires_at)
    record.token_hash = hash_token(raw_token)
    db.commit()
    set_session_cookie(response, raw_token)


def _active_session(db: Session, raw_token: str | None) -> AuthSession | None:
    if not raw_token:
        return None
    claims = decode_session_token(raw_token)
    if claims is None:
        return None
    record = db.get(AuthSession, claims["jti"])
    token_hash = hash_token(raw_token)
    if (
        record is None
        or record.user_id != claims["sub"]
        or record.revoked_at is not None
    ):
        return None
    current_hash_matches = record.token_hash == token_hash
    previous_hash_matches = (
        record.previous_token_hash == token_hash
        and record.previous_token_expires_at is not None
        and as_utc(record.previous_token_expires_at) > utcnow()
    )
    if not current_hash_matches and not previous_hash_matches:
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
    # Keep the immediately preceding JWT valid briefly. A browser can issue
    # duplicate /me requests during a refresh (notably under React StrictMode),
    # and without this overlap the first request logs the second one out.
    record.previous_token_hash = record.token_hash
    record.previous_token_expires_at = now + SESSION_ROTATION_GRACE
    record.expires_at = now + SESSION_TTL
    renewed_token = new_session_token(record.user_id, record.id, record.expires_at)
    record.token_hash = hash_token(renewed_token)
    db.commit()
    set_session_cookie(response, renewed_token)
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
    invite = None
    if body.invite_code:
        invite = db.scalar(select(InstituteInvite).where(InstituteInvite.code_hash == hash_token(body.invite_code), InstituteInvite.revoked_at.is_(None)))
        if invite is None:
            raise HTTPException(status_code=400, detail="That workspace invite code is invalid.")
        owner = db.get(User, invite.owner_user_id)
        if owner is None:
            raise HTTPException(status_code=400, detail="That workspace invite code is invalid.")
        if owner.workspace_type != invite.workspace_type:
            raise HTTPException(status_code=400, detail="That workspace invite code is invalid.")
    user = User(
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        workspace_type=owner.workspace_type if owner else body.workspace_type,
        # Keep legacy fields populated for existing integrations; access checks
        # use workspace_owner_id and workspace_role exclusively.
        institute_name=owner.workspace_name if owner else body.workspace_name,
        institute_owner_id=owner.id if owner else None,
        workspace_name=owner.workspace_name if owner else body.workspace_name,
        workspace_owner_id=owner.id if owner else None,
        workspace_role=invite.role if invite else "owner",
    )
    db.add(user)
    try:
        db.flush()
        if invite is not None and owner is not None:
            workspace_name = owner.workspace_name or owner.institute_name or "the shared workspace"
            create_notification(
                db,
                user_id=user.id,
                kind="workspace_access",
                title="Workspace access is ready",
                body=f"You joined {workspace_name} as {invite.role}.",
                resource_id=owner.id,
            )
            create_notification(
                db,
                user_id=owner.id,
                kind="member_joined",
                title="A member joined your workspace",
                body=f"A new {invite.role} member joined {workspace_name}.",
                resource_id=user.id,
            )
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


def _create_workspace_invite(
    body: WorkspaceInviteRequest,
    request: Request,
    response: Response,
    db: Session,
) -> InstituteInviteResponse:
    enforce_csrf(request)
    user = current_user(request, response, db)
    if user.workspace_type == "personal" or user.workspace_owner_id or user.institute_owner_id:
        raise HTTPException(status_code=403, detail="Only a workspace owner can create invite codes.")
    if user.workspace_type == "institution" and user.workspace_role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only an institutional admin can create invite codes.")
    role = body.role
    now = utcnow()
    # Keep a separately usable invite for each role. Rotating an editor code
    # must never silently invalidate the viewer/admin code a school already
    # shared. Only the code for this role is replaced.
    for invite in db.scalars(
        select(InstituteInvite).where(
            InstituteInvite.owner_user_id == user.id,
            InstituteInvite.role == role,
            InstituteInvite.revoked_at.is_(None),
        )
    ).all():
        invite.revoked_at = now
    code = f"PUCHOO-{secrets.token_urlsafe(7).upper()}"
    db.add(InstituteInvite(
        owner_user_id=user.id,
        code_hash=hash_token(code),
        workspace_type=user.workspace_type,
        role=role,
    ))
    db.commit()
    return InstituteInviteResponse(
        code=code,
        workspace_name=user.workspace_name or user.institute_name or "Shared workspace",
        workspace_type=user.workspace_type,
        role=role,
    )


@router.post("/workspace/invite", response_model=InstituteInviteResponse)
def create_workspace_invite(
    body: WorkspaceInviteRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> InstituteInviteResponse:
    return _create_workspace_invite(body, request, response, db)


@router.post("/institute/invite", response_model=InstituteInviteResponse)
def create_institute_invite(request: Request, response: Response, db: Session = Depends(get_db)) -> InstituteInviteResponse:
    """Compatibility route for existing institute settings screens."""
    return _create_workspace_invite(WorkspaceInviteRequest(role="viewer"), request, response, db)


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


@router.post("/email/change", response_model=OtpChallengeResponse)
def request_email_change(
    body: EmailChangeRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> OtpChallengeResponse:
    """Require the current password and an OTP delivered to the new address."""

    enforce_csrf(request)
    new_email = str(body.new_email)
    _rate_limit("email-change", request, new_email)
    if new_email == user.email:
        raise HTTPException(status_code=400, detail="Choose a different email address.")
    if db.scalar(select(User.id).where(User.email == new_email)) is not None:
        raise HTTPException(status_code=400, detail="That email address is unavailable.")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    now = utcnow()
    for row in db.scalars(
        select(EmailChangeCode).where(EmailChangeCode.user_id == user.id, EmailChangeCode.consumed_at.is_(None))
    ).all():
        row.consumed_at = now
    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    record = EmailChangeCode(
        user_id=user.id,
        new_email=new_email,
        code_hash=hash_token(raw_code),
        attempts=0,
        created_at=now,
        expires_at=now + OTP_TTL,
    )
    db.add(record)
    db.commit()
    try:
        emailer.send_otp_email(new_email, raw_code)
    except EmailDeliveryError:
        record.consumed_at = utcnow()
        db.commit()
        raise HTTPException(status_code=503, detail=EMAIL_FAILED) from None
    return OtpChallengeResponse(email=new_email)


@router.post("/email/change/verify", response_model=AuthResponse)
def verify_email_change(
    body: EmailChangeVerifyRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Commit an email address only after its one-time code is verified."""

    enforce_csrf(request)
    new_email = str(body.new_email)
    _rate_limit("email-change-verify", request, new_email)
    record = db.scalar(
        select(EmailChangeCode)
        .where(
            EmailChangeCode.user_id == user.id,
            EmailChangeCode.new_email == new_email,
            EmailChangeCode.consumed_at.is_(None),
        )
        .order_by(EmailChangeCode.created_at.desc())
    )
    now = utcnow()
    if record is None or record.attempts >= 5 or as_utc(record.expires_at) <= now or not tokens_match(record.code_hash, hash_token(body.code)):
        if record is not None:
            record.attempts += 1
            if record.attempts >= 5:
                record.consumed_at = now
            db.commit()
        raise HTTPException(status_code=401, detail=INVALID_CODE)
    existing = db.scalar(select(User.id).where(User.email == new_email, User.id != user.id))
    if existing is not None:
        raise HTTPException(status_code=400, detail="That email address is unavailable.")
    record.consumed_at = now
    user.email = new_email
    db.commit()
    return AuthResponse(user=_user_response(user))


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
