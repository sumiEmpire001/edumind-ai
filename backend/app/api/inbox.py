"""Submission-only credentials for administrator-owned local inbox services."""

import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.auth.crypto import digest, now, utc
from app.auth.dependencies import DB, Admin, trusted_origin
from app.knowledge.service import submit
from app.models.identity import User
from app.models.knowledge import InboxCredential
from app.schemas.identity import InputModel
from app.security.rate_limit import consume
from app.services.identity import audit
from app.storage.objects import configured_store

router = APIRouter(prefix="/api/v1", tags=["administrator inbox"])
inbox_bearer = HTTPBearer(auto_error=False)


class CredentialInput(InputModel):
    name: str = Field(min_length=1, max_length=100)
    valid_days: int = Field(default=30, ge=1, le=90)


def credential_view(row):
    return {
        "id": str(row.id),
        "name": row.name,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "revoked": row.revoked_at is not None,
        "last_used_at": row.last_used_at,
        "scope": "submissions:create",
    }


@router.get("/admin/inbox-credentials")
def credentials(db: DB, admin: Admin):
    return [
        credential_view(row)
        for row in db.scalars(
            select(InboxCredential)
            .where(InboxCredential.owner_id == admin.user.id)
            .order_by(InboxCredential.created_at.desc())
            .limit(100)
        )
    ]


@router.post("/admin/inbox-credentials", status_code=201, dependencies=[Depends(trusted_origin)])
def create_credential(data: CredentialInput, request: Request, db: DB, admin: Admin):
    consume(request, "inbox-mint", str(admin.user.id), 10, 3600)
    token = "emi_" + secrets.token_urlsafe(48)
    row = InboxCredential(
        owner_id=admin.user.id,
        name=data.name,
        token_hash=digest(token),
        created_at=now(),
        expires_at=now() + timedelta(days=data.valid_days),
    )
    db.add(row)
    db.flush()
    audit(db, request, "inbox.credential_created", admin.user.id, row.id)
    db.commit()
    # The raw token is returned only once, never listed, audited or logged.
    return {**credential_view(row), "token": token}


@router.delete("/admin/inbox-credentials/{cid}", dependencies=[Depends(trusted_origin)])
def revoke(cid: UUID, request: Request, db: DB, admin: Admin):
    row = db.scalar(
        select(InboxCredential)
        .where(InboxCredential.id == cid, InboxCredential.owner_id == admin.user.id)
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Credential not found.")
    row.revoked_at = now()
    audit(db, request, "inbox.credential_revoked", admin.user.id, row.id)
    db.commit()
    return {"status": "revoked"}


@router.post("/inbox/submissions", status_code=201)
async def inbox_submit(
    request: Request,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(inbox_bearer)],
    title: str = Query(min_length=1, max_length=200),
    filename: str = Query(min_length=1, max_length=200),
    description: str = Query(default="", max_length=2000),
    discipline: str = Query(default="", max_length=100),
):
    if not credentials or len(credentials.credentials) > 128:
        raise HTTPException(401, "Inbox credential required.")
    row = db.scalar(
        select(InboxCredential)
        .where(InboxCredential.token_hash == digest(credentials.credentials))
        .with_for_update()
    )
    if not row or row.revoked_at or utc(row.expires_at) <= now():
        raise HTTPException(401, "Inbox credential is invalid or expired.")
    owner = db.get(User, row.owner_id)
    if not owner or not owner.is_active or owner.role != "admin":
        raise HTTPException(403, "Inbox owner is not an active administrator.")
    consume(request, "inbox-submit", str(row.id), 30, 3600)
    row.last_used_at = now()
    data = await request.body()
    store = getattr(request.app.state, "object_store", None) or configured_store(
        request.app.state.settings
    )
    result = await run_in_threadpool(
        submit,
        db,
        request,
        owner,
        title,
        description,
        discipline,
        filename,
        request.headers.get("content-type", "").split(";")[0],
        data,
        store,
    )
    return result
