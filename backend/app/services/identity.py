from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.crypto import (
    DUMMY_HASH,
    access_token,
    digest,
    hash_password,
    now,
    random_token,
    utc,
    verify_password,
)
from app.auth.dependencies import Identity, csrf_valid, unauthorized
from app.models.identity import AuditLog, AuthSession, RefreshToken, User
from app.schemas.identity import Credentials, Registration, TokenView, UserUpdate, UserView


def audit(
    db: Session,
    request: Request,
    action: str,
    actor: UUID | None = None,
    target: UUID | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            actor_id=actor,
            target_id=target,
            request_id=request.state.request_id,
            created_at=now(),
        )
    )


def register(db: Session, request: Request, data: Registration) -> User:
    user = User(
        email=str(data.email),
        full_name=data.full_name,
        password_hash=hash_password(data.password.get_secret_value()),
        role="student",
        is_active=True,
        created_at=now(),
        updated_at=now(),
    )
    db.add(user)
    try:
        db.flush()
        audit(db, request, "user.registered", user.id, user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account cannot be created with these details.") from None
    return user


def bundle(user: User, session: AuthSession, csrf: str, request: Request) -> TokenView:
    config = request.app.state.settings
    return TokenView(
        access_token=access_token(user.id, session.id, config),
        expires_in=config.access_token_minutes * 60,
        csrf_token=csrf,
        user=UserView.model_validate(user),
    )


def login(db: Session, request: Request, data: Credentials) -> tuple[TokenView, str]:
    user = db.scalar(select(User).where(User.email == str(data.email)))
    password = data.password.get_secret_value()
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.is_active:
        audit(db, request, "auth.login_failed")
        db.commit()
        raise HTTPException(
            401, "Incorrect email or password.", headers={"WWW-Authenticate": "Bearer"}
        )
    # User lock serializes login against deactivation and password changes.
    db.refresh(user, with_for_update=True)
    if not user.is_active or not verify_password(password, user.password_hash):
        raise unauthorized()
    csrf, raw = random_token(), random_token()
    session = AuthSession(
        user_id=user.id,
        csrf_hash=digest(csrf),
        created_at=now(),
        expires_at=now() + timedelta(days=request.app.state.settings.refresh_token_days),
    )
    db.add(session)
    db.flush()
    db.add(RefreshToken(token_hash=digest(raw), session_id=session.id, created_at=now()))
    audit(db, request, "auth.login", user.id, session.id)
    db.commit()
    return bundle(user, session, csrf, request), raw


def locked_refresh(db: Session, request: Request) -> tuple[AuthSession, RefreshToken, User]:
    config = request.app.state.settings
    raw = request.cookies.get(config.refresh_cookie, "")
    if not raw or len(raw) > 128:
        raise unauthorized()
    token = db.get(RefreshToken, digest(raw))
    if token is None:
        raise unauthorized()
    # Lock order is always user -> session. Consistent with account and password changes.
    sid = token.session_id
    session = db.get(AuthSession, sid)
    if session is None:
        raise unauthorized()
    user = db.scalar(select(User).where(User.id == session.user_id).with_for_update())
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.id == sid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    token = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == digest(raw))
        .execution_options(populate_existing=True)
    )
    if (
        not session
        or session.revoked_at
        or utc(session.expires_at) <= now()
        or not user
        or not user.is_active
    ):
        raise unauthorized()
    return session, token, user


def refresh(db: Session, request: Request) -> tuple[TokenView, str]:
    session, token, user = locked_refresh(db, request)
    if not csrf_valid(request, session):
        raise HTTPException(403, "Session verification failed.")
    if token.used_at:
        session.revoked_at = now()
        audit(db, request, "auth.refresh_replay", user.id, session.id)
        db.commit()
        raise unauthorized()
    token.used_at = now()
    raw = random_token()
    db.add(RefreshToken(token_hash=digest(raw), session_id=session.id, created_at=now()))
    audit(db, request, "auth.refreshed", user.id, session.id)
    db.commit()
    csrf = request.headers["x-csrf-token"]
    return bundle(user, session, csrf, request), raw


def csrf_token(db: Session, request: Request) -> str:
    session, token, _ = locked_refresh(db, request)
    csrf = request.cookies.get(request.app.state.settings.csrf_cookie, "")
    if token.used_at or not csrf or digest(csrf) != session.csrf_hash:
        raise unauthorized()
    return csrf


def logout(db: Session, request: Request) -> None:
    raw = request.cookies.get(request.app.state.settings.refresh_cookie)
    if not raw:
        return
    # Invalid or expired credentials may be cleared, but a valid session requires CSRF.
    try:
        session, _, user = locked_refresh(db, request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return
        raise
    if not csrf_valid(request, session):
        raise HTTPException(403, "Session verification failed.")
    session.revoked_at = now()
    audit(db, request, "auth.logout", user.id, session.id)
    db.commit()


def revoke_sessions(db: Session, user_id: UUID) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )


def change_password(
    db: Session, request: Request, identity: Identity, current_password: str, new_password: str
) -> None:
    user = db.scalar(
        select(User)
        .where(User.id == identity.user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    db.refresh(identity.session)
    if (
        not user.is_active
        or identity.session.revoked_at
        or utc(identity.session.expires_at) <= now()
    ):
        raise unauthorized()
    if not verify_password(current_password, user.password_hash):
        audit(db, request, "auth.password_change_failed", user.id)
        db.commit()
        raise HTTPException(400, "Current password is incorrect.")
    if current_password == new_password:
        raise HTTPException(400, "Choose a different password.")
    user.password_hash = hash_password(new_password)
    user.updated_at = now()
    revoke_sessions(db, user.id)
    audit(db, request, "auth.password_changed", user.id, user.id)
    db.commit()


def update_user(
    db: Session, request: Request, actor: User, user_id: UUID, data: UserUpdate
) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(404, "User not found.")
    # Admin management stays out of public APIs; protects the last admin and the actor.
    if user.id == actor.id or user.role == "admin":
        raise HTTPException(409, "Administrator accounts require private maintenance.")
    if data.role is None and data.is_active is None:
        raise HTTPException(422, "Provide an account status or role.")
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    user.updated_at = now()
    revoke_sessions(db, user.id)
    audit(db, request, "admin.user_updated", actor.id, user.id)
    db.commit()
    return user


def list_users(db: Session, offset: int, limit: int) -> tuple[list[User], int]:
    total = db.scalar(select(func.count()).select_from(User))
    users = list(
        db.scalars(select(User).order_by(User.created_at, User.id).offset(offset).limit(limit))
    )
    return users, total
