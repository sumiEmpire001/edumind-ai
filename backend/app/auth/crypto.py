import hashlib
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore
from uuid import UUID

import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import Settings

password_hasher = PasswordHash.recommended()
# A missing account still performs password verification to reduce timing differences.
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
_hash_slots = BoundedSemaphore(4)


@contextmanager
def hashing_slot() -> Iterator[None]:
    # Bound Argon2 memory use within each process, independently of distributed quotas.
    if not _hash_slots.acquire(timeout=0.25):
        raise HTTPException(
            503, "The service is busy. Please try again.", headers={"Retry-After": "1"}
        )
    try:
        yield
    finally:
        _hash_slots.release()


def hash_password(password: str) -> str:
    with hashing_slot():
        return password_hasher.hash(password)


def now() -> datetime:
    return datetime.now(UTC)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def random_token() -> str:
    return secrets.token_urlsafe(48)


def verify_password(password: str, hashed: str) -> bool:
    with hashing_slot():
        try:
            return password_hasher.verify(password, hashed)
        except (ValueError, UnknownHashError):
            return False


def access_token(user_id: UUID, session_id: UUID, settings: Settings) -> str:
    issued = now()
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "type": "access",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": issued,
            "nbf": issued,
            "exp": issued + timedelta(minutes=settings.access_token_minutes),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access(token: str, settings: Settings) -> tuple[UUID, UUID]:
    claims = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["sub", "sid", "type", "iat", "nbf", "exp"]},
    )
    if claims["type"] != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    try:
        return UUID(claims["sub"]), UUID(claims["sid"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise jwt.InvalidTokenError("Invalid token subject") from exc
