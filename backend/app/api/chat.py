from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import DB, Current
from app.schemas.chat import (
    ConversationCreate,
    ConversationDetail,
    ConversationPage,
    ConversationUpdate,
    ConversationView,
    TurnCreate,
    TurnResult,
)
from app.security.rate_limit import consume
from app.services import chat as service

router = APIRouter(prefix="/api/v1", tags=["conversations"])


def write_limit(request: Request, owner: UUID) -> None:
    consume(request, "chat-write", str(owner), request.app.state.settings.chat_user_limit, 60)


@router.get("/chat/capabilities")
def capabilities(request: Request, identity: Current):
    provider = request.app.state.academic_provider
    settings = request.app.state.settings
    return {
        "available": provider.available,
        "mode": provider.mode,
        "timeout_seconds": request.app.state.settings.chat_timeout_seconds,
        "attachments_available": bool(
            getattr(request.app.state, "object_store", None)
            or (settings.blob_store_id and settings.blob_read_write_token)
            or (
                settings.storage_bucket
                and settings.storage_access_key
                and settings.storage_secret_key
            )
        ),
        "attachment_types": ["image/png", "image/jpeg", "text/plain"],
        "image_generation": False,
    }


@router.get("/conversations", response_model=ConversationPage)
def listing(
    db: DB, identity: Current, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)
):
    return service.listing(db, identity.user.id, offset, limit)


@router.post("/conversations", response_model=ConversationView, status_code=201)
def create(data: ConversationCreate, request: Request, db: DB, identity: Current):
    write_limit(request, identity.user.id)
    return service.create(db, identity.user.id, data.client_id, request.state.request_id)


@router.get("/conversations/{cid}", response_model=ConversationDetail)
def detail(
    cid: UUID,
    db: DB,
    identity: Current,
    before_sequence: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=100),
):
    service.regular_owned(db, identity.user.id, cid)
    return service.detail(db, identity.user.id, cid, before_sequence, limit)


@router.patch("/conversations/{cid}", response_model=ConversationView)
def rename(cid: UUID, data: ConversationUpdate, request: Request, db: DB, identity: Current):
    service.regular_owned(db, identity.user.id, cid)
    write_limit(request, identity.user.id)
    return service.rename(db, identity.user.id, cid, data.title, request.state.request_id)


@router.delete("/conversations/{cid}", status_code=204)
def remove(cid: UUID, request: Request, db: DB, identity: Current):
    service.regular_owned(db, identity.user.id, cid, include_deleted=True)
    write_limit(request, identity.user.id)
    service.remove(db, identity.user.id, cid, request.state.request_id)


@router.post("/conversations/{cid}/messages", response_model=TurnResult)
async def submit(
    cid: UUID, data: TurnCreate, request: Request, response: Response, db: DB, identity: Current
):
    owner, sid = identity.user.id, identity.session.id
    service.regular_owned(db, owner, cid)
    # Release the authentication read transaction before waiting on any provider call.
    db.rollback()
    await run_in_threadpool(write_limit, request, owner)
    from fastapi import HTTPException

    from app.api.attachments import storage

    try:
        store = storage(request)
    except HTTPException:
        store = None
    result = await service.submit(
        request.app.state.engine,
        owner,
        sid,
        cid,
        data,
        request.app.state.academic_provider,
        request.app.state.settings,
        request.state.request_id,
        store,
    )
    if result.request.status == "pending":
        response.status_code = 202
        response.headers["Retry-After"] = "2"
    elif result.request.status == "failed":
        response.status_code = {
            "timeout": 504,
            "interrupted": 504,
            "rate_limited": 429,
            "unavailable": 503,
        }.get(result.request.error_code, 502)
        if response.status_code == 429:
            response.headers["Retry-After"] = "3"
    else:
        response.status_code = 200 if result.replayed else 201
    return result
