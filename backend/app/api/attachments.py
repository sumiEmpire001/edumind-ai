import base64
import io
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.crypto import now
from app.auth.dependencies import DB, Current
from app.models.identity import User
from app.models.studio import ChatAttachment
from app.security.rate_limit import consume
from app.services import attachments, chat
from app.storage.objects import configured_store

router = APIRouter(prefix="/api/v1", tags=["personal attachments"])


def storage(request):
    return getattr(request.app.state, "object_store", None) or configured_store(
        request.app.state.settings
    )


@router.post("/conversations/{cid}/attachments", status_code=201)
async def upload(
    cid: UUID,
    request: Request,
    db: DB,
    identity: Current,
    filename: str = Query(min_length=1, max_length=160),
):
    owner, sid = identity.user.id, identity.session.id
    db.rollback()
    filename = PurePosixPath(filename.replace("\\", "/")).name
    if not filename or any(ord(c) < 32 for c in filename):
        raise HTTPException(422, "Use a valid filename.")
    await run_in_threadpool(consume, request, "personal-upload", str(owner), 20, 3600)
    raw = await request.body()
    data, mime = await run_in_threadpool(
        attachments.validate, filename, raw, request.headers.get("content-type", "")
    )
    return await run_in_threadpool(
        persist, request.app.state.engine, owner, sid, cid, filename, data, mime, storage(request)
    )


def persist(engine, owner, sid, cid, filename, data, mime, store):
    with Session(engine, expire_on_commit=False) as db:
        chat.live_identity(db, owner, sid)
        # Per-owner quota updates serialize without blocking the ASGI event loop.
        db.scalar(select(User).where(User.id == owner).with_for_update())
        chat.owned(db, owner, cid, lock=True)
        unbound = db.scalar(
            select(func.count())
            .select_from(ChatAttachment)
            .where(
                ChatAttachment.conversation_id == cid,
                ChatAttachment.request_id.is_(None),
                ChatAttachment.deleted_at.is_(None),
            )
        )
        if unbound >= 2:
            raise HTTPException(409, "Use or remove the two pending attachments first.")
        size = db.scalar(
            select(func.coalesce(func.sum(ChatAttachment.size), 0)).where(
                ChatAttachment.owner_id == owner, ChatAttachment.deleted_at.is_(None)
            )
        )
        count = db.scalar(
            select(func.count())
            .select_from(ChatAttachment)
            .where(ChatAttachment.owner_id == owner, ChatAttachment.deleted_at.is_(None))
        )
        if size + len(data) > 20 * 1024 * 1024 or count >= 50:
            raise HTTPException(409, "Personal attachment limit reached.")
        key = "personal/" + str(owner) + "/" + uuid4().hex
        try:
            store.put(key, data, mime)
        except Exception:
            raise HTTPException(503, "Private attachment storage is unavailable.") from None
        row = ChatAttachment(
            owner_id=owner,
            conversation_id=cid,
            filename=filename,
            mime=mime,
            size=len(data),
            object_key=key,
            created_at=now(),
        )
        db.add(row)
        try:
            db.expire_all()
            chat.live_identity(db, owner, sid)
            db.commit()
        except Exception:
            db.rollback()
            try:
                store.delete(key)
            except Exception:
                pass
            raise
        return attachments.view(row)


@router.get("/conversations/{cid}/attachments")
def pending(cid: UUID, db: DB, identity: Current):
    chat.owned(db, identity.user.id, cid)
    return [
        attachments.view(row)
        for row in db.scalars(
            select(ChatAttachment)
            .where(
                ChatAttachment.owner_id == identity.user.id,
                ChatAttachment.conversation_id == cid,
                ChatAttachment.request_id.is_(None),
                ChatAttachment.deleted_at.is_(None),
            )
            .order_by(ChatAttachment.created_at)
            .limit(2)
        )
    ]


@router.get("/conversations/{cid}/attachments/{aid}/preview")
def preview(cid: UUID, aid: UUID, request: Request, db: DB, identity: Current):
    chat.owned(db, identity.user.id, cid)
    row = db.scalar(
        select(ChatAttachment).where(
            ChatAttachment.id == aid,
            ChatAttachment.owner_id == identity.user.id,
            ChatAttachment.conversation_id == cid,
            ChatAttachment.deleted_at.is_(None),
        )
    )
    if row is None or row.mime not in {"image/jpeg", "image/png"}:
        raise HTTPException(404, "Image not found.")
    try:
        data = storage(request).get(row.object_key)
        if len(data) > attachments.MAX_BYTES:
            raise ValueError()
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > attachments.MAX_PIXELS:
                raise ValueError()
            image.thumbnail((360, 360))
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=80)
    except Exception:
        raise HTTPException(503, "Image preview is unavailable.") from None
    return {"mime": "image/jpeg", "base64": base64.b64encode(output.getvalue()).decode()}


@router.delete("/conversations/{cid}/attachments/{aid}", status_code=204)
def discard(cid: UUID, aid: UUID, request: Request, db: DB, identity: Current):
    from fastapi import HTTPException

    chat.owned(db, identity.user.id, cid, lock=True)
    row = db.scalar(
        select(ChatAttachment)
        .where(
            ChatAttachment.id == aid,
            ChatAttachment.owner_id == identity.user.id,
            ChatAttachment.conversation_id == cid,
            ChatAttachment.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Attachment not found.")
    if row.request_id:
        raise HTTPException(409, "Used attachments follow the conversation retention policy.")
    try:
        storage(request).delete(row.object_key)
    except Exception:
        raise HTTPException(503, "Could not remove the private attachment.") from None
    row.deleted_at = now()
    db.commit()
