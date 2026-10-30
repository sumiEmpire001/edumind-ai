import secrets
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.crypto import decode_access, digest, now, utc
from app.database.dependencies import get_db
from app.models.identity import AuthSession, User

bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]


def unauthorized() -> HTTPException:
    return HTTPException(
        401, "Authentication required or session expired.", headers={"WWW-Authenticate": "Bearer"}
    )


@dataclass
class Identity:
    user: User
    session: AuthSession


def current_identity(
    request: Request,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Identity:
    if credentials is None or len(credentials.credentials) > 4096:
        raise unauthorized()
    try:
        uid, sid = decode_access(credentials.credentials, request.app.state.settings)
    except jwt.InvalidTokenError:
        raise unauthorized() from None
    session = db.get(AuthSession, sid)
    user = db.get(User, uid)
    if (
        not session
        or session.user_id != uid
        or session.revoked_at
        or utc(session.expires_at) <= now()
        or not user
        or not user.is_active
    ):
        raise unauthorized()
    return Identity(user, session)


Current = Annotated[Identity, Depends(current_identity)]


def administrator(identity: Current) -> Identity:
    if identity.user.role != "admin":
        raise HTTPException(403, "Administrator access required.")
    return identity


Admin = Annotated[Identity, Depends(administrator)]


def trusted_origin(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.settings.cors_origins:
        raise HTTPException(403, "Request origin is not permitted.")


def csrf_valid(request: Request, session: AuthSession) -> bool:
    settings = request.app.state.settings
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(settings.csrf_cookie, "")
    return bool(
        header
        and cookie
        and header.isascii()
        and cookie.isascii()
        and len(header) <= 128
        and secrets.compare_digest(header, cookie)
        and secrets.compare_digest(digest(header), session.csrf_hash)
    )
