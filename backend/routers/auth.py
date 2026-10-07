"""Signup, login, logout, and the current-user endpoint."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import emailer
from backend.config import settings
from backend.database import get_db
from backend.emailer import EmailDeliveryError
from backend.models import (
    AuthSession,
    EmailChangeCode,
    InstituteInvite,
    LoginChallenge,
    PasswordResetCode,
    User,
)
from backend.notifications import create_notification
from backend.rate_limit import authenticated_limiter, limiter, public_limiter
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
    WorkspaceMemberResponse,
    WorkspaceMemberRoleRequest,
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
    clear_login_challenge_cookie,
    hash_otp,
    hash_password,
    hash_token,
    new_session_token,
    otp_matches,
    set_login_challenge_cookie,
    set_session_cookie,
    tokens_match,
    utcnow,
    verify_password,
    verify_password_for_missing_user,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
OTP_TTL = timedelta(minutes=5)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CHALLENGE_ATTEMPTS = 5
MAX_RESENDS = 3
SESSION_ROTATION_GRACE = timedelta(minutes=2)
# Renew only close to expiry. Per-request rotation races with parallel browser
# calls and SSE connections, while this preserves a seven-day sliding session.
SESSION_RENEWAL_WINDOW = timedelta(hours=24)
INVALID_CODE = "That code is invalid or has expired."
LOGIN_EXPIRED = "Login session expired, please sign in again"
EMAIL_FAILED = "We could not send the verification email. Try again in a moment."
RESEND_COOLDOWN_ERROR = "Please wait before requesting another code."
RESEND_LIMIT_ERROR = "Too many codes were sent. Check your email for the latest code or sign in again."
INVITE_TTL = timedelta(days=7)


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def _invite_expired(invite: InstituteInvite, now: datetime) -> bool:
    expiry = invite.expires_at or (as_utc(invite.created_at) + INVITE_TTL)
    return as_utc(expiry) <= now


def _workspace_member_response(user: User, tenant_id: str) -> WorkspaceMemberResponse:
    return WorkspaceMemberResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role="owner" if user.id == tenant_id else user.workspace_role,
    )


def _managed_workspace_member(db: Session, tenant_id: str, member_id: str) -> User:
    member = db.get(User, member_id)
    if member is None or member.id == tenant_id or member.workspace_owner_id != tenant_id:
        raise HTTPException(status_code=404, detail="Workspace member not found")
    return member


def _rate_limit(action: str, request: Request, email: str) -> None:
    allowed, retry_after = limiter.allow_with_backoff(
        [
            f"{action}:ip:{client_ip(request)}",
            f"{action}:account:{email}",
        ]
    )
    if not allowed:
        raise HTTPException(status_code=429, detail=RATE_LIMIT_ERROR, headers={"Retry-After": str(retry_after)})


def _rate_limit_ip(action: str, request: Request) -> None:
    allowed, retry_after = limiter.allow_with_backoff([f"{action}:ip:{client_ip(request)}"])
    if not allowed:
        raise HTTPException(status_code=429, detail=RATE_LIMIT_ERROR, headers={"Retry-After": str(retry_after)})


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
    record = _active_session(db, request.cookies.get(settings.session_cookie_name))
    if record is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not authenticated_limiter.allow([f"user:{record.user_id}"]):
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMIT_ERROR,
            headers={"Retry-After": str(settings.authenticated_rate_window_seconds)},
        )
    # Keep a signed session stable during normal use. Per-request rotation is
    # unsafe in a browser: parallel calls (including an SSE connection) can
    # return Set-Cookie headers out of order and strand the client with a token
    # that the database no longer recognizes. Renew only near expiry, retaining
    # a short overlap for duplicate requests in that renewal window.
    now = utcnow()
    if as_utc(record.expires_at) <= now + SESSION_RENEWAL_WINDOW:
        record.previous_token_hash = record.token_hash
        record.previous_token_expires_at = now + SESSION_ROTATION_GRACE
        record.expires_at = now + SESSION_TTL
        renewed_token = new_session_token(record.user_id, record.id, record.expires_at)
        record.token_hash = hash_token(renewed_token)
        db.commit()
        set_session_cookie(response, renewed_token)
    return record.user


@router.get("/csrf", status_code=204)
def issue_csrf(request: Request) -> Response:
    """The CSRF cookie middleware attaches the double-submit cookie."""

    if not public_limiter.allow([f"csrf:ip:{client_ip(request)}"]):
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMIT_ERROR,
            headers={"Retry-After": str(settings.public_rate_window_seconds)},
        )
    return Response(status_code=204)


@router.post("/signup", response_model=OtpChallengeResponse, response_model_exclude_none=True, status_code=202)
def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> OtpChallengeResponse:
    enforce_csrf(request)
    _rate_limit("signup", request, body.email)
    owner = None
    invite = None
    if body.invite_code:
        invite = db.scalar(select(InstituteInvite).where(InstituteInvite.code_hash == hash_token(body.invite_code), InstituteInvite.revoked_at.is_(None)))
        if invite is None or _invite_expired(invite, utcnow()):
            raise HTTPException(status_code=400, detail="That workspace invite code is invalid.")
        owner = db.get(User, invite.owner_user_id)
        if owner is None:
            raise HTTPException(status_code=400, detail="That workspace invite code is invalid.")
        if owner.workspace_type != invite.workspace_type:
            raise HTTPException(status_code=400, detail="That workspace invite code is invalid.")
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        # Same status and body as a new signup. Do not send a login code:
        # that would let the caller skip the password.
        hash_password(body.password)
        return OtpChallengeResponse(email=body.email)
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
    record, raw_code = _create_login_challenge(db, user)
    try:
        emailer.send_otp_email(user.email, raw_code)
    except EmailDeliveryError:
        # Do not leave an unreachable account behind when delivery is unavailable.
        _delete_user_and_challenges(db, user)
        raise HTTPException(status_code=503, detail=EMAIL_FAILED) from None
    set_login_challenge_cookie(response, record.id)
    return OtpChallengeResponse(email=user.email)


def _create_workspace_invite(
    body: WorkspaceInviteRequest,
    request: Request,
    response: Response,
    db: Session,
) -> InstituteInviteResponse:
    enforce_csrf(request)
    user = current_user(request, response, db)
    # Import here to avoid the auth <-> product-router import cycle at startup.
    from apps.api.security import can_administer_workspace, tenant_owner_id

    if user.workspace_type == "personal" or not can_administer_workspace(user):
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can create invite codes.")
    tenant_id = tenant_owner_id(user)
    tenant_owner = db.get(User, tenant_id)
    if tenant_owner is None:
        raise HTTPException(status_code=403, detail="The shared workspace is unavailable.")
    role = body.role
    now = utcnow()
    # Keep a separately usable invite for each role. Rotating an editor code
    # must never silently invalidate the viewer/admin code a school already
    # shared. Only the code for this role is replaced.
    for invite in db.scalars(
        select(InstituteInvite).where(
            InstituteInvite.owner_user_id == tenant_id,
            InstituteInvite.role == role,
            InstituteInvite.revoked_at.is_(None),
        )
    ).all():
        invite.revoked_at = now
    code = f"PUCHOO-{secrets.token_urlsafe(7).upper()}"
    db.add(InstituteInvite(
        owner_user_id=tenant_id,
        code_hash=hash_token(code),
        workspace_type=user.workspace_type,
        role=role,
        expires_at=now + INVITE_TTL,
    ))
    db.commit()
    return InstituteInviteResponse(
        code=code,
        workspace_name=tenant_owner.workspace_name or tenant_owner.institute_name or "Shared workspace",
        workspace_type=tenant_owner.workspace_type,
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


@router.get("/workspace/members", response_model=list[WorkspaceMemberResponse])
def list_workspace_members(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceMemberResponse]:
    from apps.api.security import tenant_owner_id

    tenant_id = tenant_owner_id(user)
    if user.workspace_type == "personal":
        return [_workspace_member_response(user, tenant_id)]
    members = db.scalars(
        select(User).where((User.id == tenant_id) | (User.workspace_owner_id == tenant_id)).order_by(User.created_at)
    ).all()
    return [_workspace_member_response(member, tenant_id) for member in members]


@router.patch("/workspace/members/{member_id}", response_model=WorkspaceMemberResponse)
def update_workspace_member_role(
    member_id: str,
    body: WorkspaceMemberRoleRequest,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMemberResponse:
    from apps.api.security import can_administer_workspace, tenant_owner_id

    enforce_csrf(request)
    if not can_administer_workspace(user):
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can manage members.")
    tenant_id = tenant_owner_id(user)
    member = _managed_workspace_member(db, tenant_id, member_id)
    member.workspace_role = body.role
    db.commit()
    return _workspace_member_response(member, tenant_id)


@router.delete("/workspace/members/{member_id}", status_code=204)
def remove_workspace_member(
    member_id: str,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    from apps.api.security import can_administer_workspace, tenant_owner_id

    enforce_csrf(request)
    if not can_administer_workspace(user):
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can manage members.")
    member = _managed_workspace_member(db, tenant_owner_id(user), member_id)
    now = utcnow()
    _revoke_sessions_and_challenges(db, member.id, now)
    member.workspace_type = "personal"
    member.workspace_name = None
    member.workspace_owner_id = None
    member.workspace_role = "owner"
    member.institute_name = None
    member.institute_owner_id = None
    db.commit()
    return Response(status_code=204)


def _new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _delete_user_and_challenges(db: Session, user: User) -> None:
    for row in db.scalars(select(LoginChallenge).where(LoginChallenge.user_id == user.id)).all():
        db.delete(row)
    db.delete(user)
    db.commit()


def _create_login_challenge(db: Session, user: User) -> tuple[LoginChallenge, str]:
    """Open one password-proven challenge and retire any older unused ones."""

    now = utcnow()
    pending = db.scalars(
        select(LoginChallenge).where(LoginChallenge.user_id == user.id, LoginChallenge.consumed_at.is_(None))
    ).all()
    for row in pending:
        row.consumed_at = now
    raw_code = _new_otp()
    record = LoginChallenge(
        user_id=user.id,
        code_hash=hash_otp(raw_code),
        attempts=0,
        resend_count=0,
        created_at=now,
        expires_at=now + OTP_TTL,
        last_sent_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, raw_code


def _challenge_row(request: Request, db: Session) -> LoginChallenge | None:
    from backend.config import settings

    challenge_id = request.cookies.get(settings.login_challenge_cookie_name)
    if not challenge_id:
        return None
    return db.get(LoginChallenge, challenge_id)


def _challenge_is_open(record: LoginChallenge) -> bool:
    if record.consumed_at is not None or record.locked_at is not None:
        return False
    if record.attempts >= MAX_CHALLENGE_ATTEMPTS:
        return False
    return as_utc(record.expires_at) > utcnow()


def _open_challenge(request: Request, response: Response, db: Session) -> LoginChallenge:
    record = _challenge_row(request, db)
    if record is None:
        _rate_limit_ip("verify", request)
        _reject_login_challenge(response)
    if not _challenge_is_open(record):
        _reject_login_challenge(response)
    return record


def _reject_login_challenge(response: Response) -> NoReturn:
    clear_login_challenge_cookie(response)
    raise HTTPException(status_code=400, detail=LOGIN_EXPIRED)


def _register_failed_attempt(db: Session, challenge_id: str) -> bool:
    """Atomically count one wrong code. Return True when this try locks the challenge.

    One conditional UPDATE is the lock, on SQLite and Postgres. A parallel
    request cannot increment past five because the predicate is attempts < 5.
    """

    now = utcnow()
    row = db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.id == challenge_id,
            LoginChallenge.attempts < MAX_CHALLENGE_ATTEMPTS,
            LoginChallenge.consumed_at.is_(None),
        )
        .values(
            attempts=LoginChallenge.attempts + 1,
            locked_at=case(
                (LoginChallenge.attempts + 1 >= MAX_CHALLENGE_ATTEMPTS, now),
                else_=LoginChallenge.locked_at,
            ),
        )
        .returning(LoginChallenge.attempts)
        .execution_options(synchronize_session=False)
    ).first()
    db.commit()
    if row is None:
        return True
    return row.attempts >= MAX_CHALLENGE_ATTEMPTS


def _consume_challenge(db: Session, challenge_id: str, now: datetime) -> bool:
    result = db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.id == challenge_id,
            LoginChallenge.attempts < MAX_CHALLENGE_ATTEMPTS,
            LoginChallenge.consumed_at.is_(None),
            LoginChallenge.locked_at.is_(None),
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def _revoke_sessions_and_challenges(db: Session, user_id: str, now: datetime) -> None:
    sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ).all()
    for record in sessions:
        record.revoked_at = now
    challenges = db.scalars(
        select(LoginChallenge).where(LoginChallenge.user_id == user_id, LoginChallenge.consumed_at.is_(None))
    ).all()
    for challenge in challenges:
        challenge.consumed_at = now
        if challenge.locked_at is None:
            challenge.locked_at = now


@router.post("/login", response_model=OtpChallengeResponse, response_model_exclude_none=True)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
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
    record, raw_code = _create_login_challenge(db, user)
    try:
        emailer.send_otp_email(user.email, raw_code)
    except EmailDeliveryError:
        record.consumed_at = utcnow()
        db.commit()
        clear_login_challenge_cookie(response)
        logger.warning("login verification email could not be sent")
        raise HTTPException(status_code=503, detail=EMAIL_FAILED) from None
    set_login_challenge_cookie(response, record.id)
    return OtpChallengeResponse(email=user.email)


@router.post("/login/resend", response_model=OtpChallengeResponse, response_model_exclude_none=True)
def resend_login_code(
    body: ResendOtpRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> OtpChallengeResponse:
    """Replace the code on the password-proven challenge named by the cookie."""

    enforce_csrf(request)
    challenge = _open_challenge(request, response, db)
    _rate_limit_ip("resend", request)
    user = db.get(User, challenge.user_id)
    if user is None:
        _reject_login_challenge(response)
    now = utcnow()
    if challenge.resend_count >= MAX_RESENDS:
        raise HTTPException(status_code=429, detail=RESEND_LIMIT_ERROR)
    if as_utc(challenge.last_sent_at) + RESEND_COOLDOWN > now:
        raise HTTPException(status_code=429, detail=RESEND_COOLDOWN_ERROR, headers={"Retry-After": "60"})
    raw_code = _new_otp()
    result = db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.id == challenge.id,
            LoginChallenge.resend_count < MAX_RESENDS,
            LoginChallenge.consumed_at.is_(None),
            LoginChallenge.locked_at.is_(None),
            LoginChallenge.last_sent_at <= now - RESEND_COOLDOWN,
        )
        .values(
            code_hash=hash_otp(raw_code),
            resend_count=LoginChallenge.resend_count + 1,
            last_sent_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=429, detail=RESEND_COOLDOWN_ERROR, headers={"Retry-After": "60"})
    try:
        emailer.send_otp_email(user.email, raw_code)
    except EmailDeliveryError:
        db.rollback()
        raise HTTPException(status_code=503, detail=EMAIL_FAILED) from None
    db.commit()
    return OtpChallengeResponse(email=user.email)


@router.post("/password/forgot", response_model=OtpChallengeResponse, response_model_exclude_none=True)
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
    now = utcnow()
    record.consumed_at = now
    assert user is not None
    user.password_hash = hash_password(body.password)
    _revoke_sessions_and_challenges(db, user.id, now)
    db.commit()
    return {"ok": True}


@router.post("/email/change", response_model=OtpChallengeResponse, response_model_exclude_none=True)
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
    response: Response,
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
    old_email = user.email
    record.consumed_at = now
    user.email = new_email
    _revoke_sessions_and_challenges(db, user.id, now)
    _issue_session(db, user, response)
    try:
        emailer.send_email_changed_notice(old_email)
    except EmailDeliveryError:
        logger.warning("email change notice could not be sent")
    return AuthResponse(user=_user_response(user))


@router.post("/login/verify", response_model=AuthResponse)
def verify_login(
    body: VerifyLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    enforce_csrf(request)
    record = _open_challenge(request, response, db)
    user = db.get(User, record.user_id)
    if user is None:
        _reject_login_challenge(response)
    _rate_limit("verify", request, user.email)
    now = utcnow()
    code_is_valid = otp_matches(body.code, record.code_hash)
    if not code_is_valid:
        locked = _register_failed_attempt(db, record.id)
        if locked:
            _reject_login_challenge(response)
        raise HTTPException(status_code=401, detail=INVALID_CODE)
    if not _consume_challenge(db, record.id, now):
        db.rollback()
        _reject_login_challenge(response)
    clear_login_challenge_cookie(response)
    first_name = user.full_name.strip().split(maxsplit=1)[0] or "there"
    create_notification(
        db,
        user_id=user.id,
        kind="session_started",
        title=f"Welcome, {first_name}",
        body="Your secure workspace is ready. Ask a question whenever you are ready.",
    )
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
    clear_login_challenge_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
    return _user_response(user)
