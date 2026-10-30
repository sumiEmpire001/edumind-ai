import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.ai.provider import AcademicError, AcademicProvider, Turn
from app.auth.crypto import now, utc
from app.auth.dependencies import unauthorized
from app.core.config import Settings
from app.models.chat import ChatRequest, Conversation, Message
from app.models.identity import AuditLog, AuthSession, User
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSubmission,
    MessageSource,
)
from app.models.studio import ChatAttachment
from app.schemas.chat import (
    ConversationDetail,
    ConversationView,
    MessageView,
    RequestView,
    TurnCreate,
    TurnResult,
)
from app.services.attachments import attach_turn, question_hash

logger = logging.getLogger("edumind")


def event(db: Session, actor: UUID, action: str, target: UUID, trace: str) -> None:
    db.add(
        AuditLog(
            actor_id=actor, action=action, target_id=target, request_id=trace, created_at=now()
        )
    )


def owned(db: Session, owner: UUID, cid: UUID, lock=False, include_deleted=False) -> Conversation:
    query = select(Conversation).where(Conversation.id == cid, Conversation.owner_id == owner)
    if not include_deleted:
        query = query.where(Conversation.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    row = db.scalar(query.execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "Conversation not found.")
    return row


def create(db: Session, owner: UUID, client_id: UUID, trace: str) -> Conversation:
    existing = db.get(Conversation, client_id)
    if existing:
        if existing.owner_id != owner or existing.deleted_at:
            raise HTTPException(409, "This conversation identifier cannot be used.")
        return existing
    row = Conversation(
        id=client_id,
        owner_id=owner,
        title="New conversation",
        automatic_title=True,
        last_sequence=0,
        created_at=now(),
        updated_at=now(),
    )
    db.add(row)
    try:
        db.flush()
        event(db, owner, "chat.created", row.id, trace)
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.get(Conversation, client_id)
        if not row or row.owner_id != owner or row.deleted_at:
            raise HTTPException(409, "This conversation identifier cannot be used.") from None
    return row


def listing(db: Session, owner: UUID, offset: int, limit: int):
    conditions = (Conversation.owner_id == owner, Conversation.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(Conversation).where(*conditions))
    items = list(
        db.scalars(
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc(), Conversation.id)
            .offset(offset)
            .limit(limit)
        )
    )
    return {"items": items, "total": total, "offset": offset, "limit": limit}


def detail(
    db: Session, owner: UUID, cid: UUID, before: int | None, limit: int
) -> ConversationDetail:
    row = owned(db, owner, cid)
    query = select(Message).where(Message.conversation_id == cid)
    if before:
        query = query.where(Message.sequence < before)
    messages = list(db.scalars(query.order_by(Message.sequence.desc()).limit(limit)))
    messages.reverse()
    request_ids = {m.request_id for m in messages}
    requests = (
        list(db.scalars(select(ChatRequest).where(ChatRequest.id.in_(request_ids))))
        if request_ids
        else []
    )
    return ConversationDetail(
        conversation=ConversationView.model_validate(row),
        messages=[MessageView.model_validate(m) for m in messages],
        requests=[RequestView.from_record(q) for q in requests],
        has_older=bool(messages and messages[0].sequence > 1),
    )


def rename(db: Session, owner: UUID, cid: UUID, title: str, trace: str) -> Conversation:
    row = owned(db, owner, cid, lock=True)
    row.title, row.automatic_title, row.updated_at = title, False, now()
    event(db, owner, "chat.renamed", cid, trace)
    db.commit()
    return row


def remove(db: Session, owner: UUID, cid: UUID, trace: str) -> None:
    row = owned(db, owner, cid, lock=True, include_deleted=True)
    if row.deleted_at is None:
        row.deleted_at = now()
        event(db, owner, "chat.removed", cid, trace)
        db.commit()


def live_identity(db: Session, owner: UUID, sid: UUID) -> None:
    user, session = db.get(User, owner), db.get(AuthSession, sid)
    if (
        not user
        or not user.is_active
        or not session
        or session.user_id != owner
        or session.revoked_at
        or utc(session.expires_at) <= now()
    ):
        raise unauthorized()


def result(db: Session, request: ChatRequest, replayed: bool) -> TurnResult:
    messages = db.scalars(
        select(Message).where(Message.request_id == request.id).order_by(Message.sequence)
    )
    return TurnResult(
        request=RequestView.from_record(request),
        messages=[MessageView.model_validate(m) for m in messages],
        replayed=replayed,
    )


def fail(request: ChatRequest, code: str) -> None:
    request.status, request.error_code, request.completed_at = "failed", code, now()


@dataclass
class Ticket:
    context: list[Turn]
    cached: TurnResult | None = None


def prepare(
    engine: Engine,
    owner: UUID,
    sid: UUID,
    cid: UUID,
    data: TurnCreate,
    config: Settings,
    available: bool,
    trace: str,
    store=None,
) -> Ticket:
    with Session(engine, expire_on_commit=False) as db:
        live_identity(db, owner, sid)
        row = owned(db, owner, cid, lock=True)
        existing = db.get(ChatRequest, data.request_id)
        if existing:
            if existing.conversation_id != cid or existing.content_hash != question_hash(data):
                raise HTTPException(
                    409, "This request identifier was already used for another question."
                )
            if existing.status == "pending" and utc(existing.deadline_at) <= now():
                fail(existing, "interrupted")
                db.commit()
            return Ticket([], result(db, existing, True))
        if not available:
            raise HTTPException(503, "Academic answers are not connected yet.")
        current_turn, attachment_metadata = attach_turn(
            db, owner, cid, data.content, data.attachment_ids, store, data.request_id
        )
        active = list(
            db.scalars(
                select(ChatRequest).where(
                    ChatRequest.conversation_id == cid, ChatRequest.status == "pending"
                )
            )
        )
        for item in active:
            if utc(item.deadline_at) > now():
                raise HTTPException(
                    409, "A question is already being processed in this conversation."
                )
            fail(item, "interrupted")
        db.flush()
        # Completed pairs only; never mix owners/conversations, pending work, or failed questions.
        previous = list(
            db.scalars(
                select(Message)
                .join(ChatRequest, Message.request_id == ChatRequest.id)
                .where(Message.conversation_id == cid, ChatRequest.status == "succeeded")
                .order_by(Message.sequence.desc())
                .limit(20)
            )
        )
        pairs, used = [], len(current_turn.content)
        for index in range(0, len(previous), 2):
            pair = previous[index : index + 2]
            if len(pair) != 2 or pair[0].role != "assistant" or pair[1].role != "user":
                raise HTTPException(503, "Conversation history is temporarily unavailable.")
            past = Turn("user", pair[1].content)
            if pair[1].attachments:
                if index < 4:
                    past, _ = attach_turn(
                        db,
                        owner,
                        cid,
                        pair[1].content,
                        [item["id"] for item in pair[1].attachments],
                        store,
                    )
                else:
                    past = Turn(
                        "user",
                        pair[1].content
                        + "\n[Earlier attachments omitted; ask for reattachment if needed.]",
                    )
            cost = len(past.content) + len(pair[0].content)
            if used + cost > config.chat_context_characters:
                break
            used += cost
            pairs.append([past, Turn("assistant", pair[0].content)])
        context = [turn for pair in reversed(pairs) for turn in pair] + [current_turn]
        request = ChatRequest(
            id=data.request_id,
            conversation_id=cid,
            content_hash=question_hash(data),
            status="pending",
            created_at=now(),
            deadline_at=now() + timedelta(seconds=config.chat_timeout_seconds + 10),
        )
        db.add(request)
        db.flush()
        for identifier in data.attachment_ids:
            db.get(ChatAttachment, identifier).request_id = request.id
        row.last_sequence += 1
        db.add(
            Message(
                conversation_id=cid,
                request_id=request.id,
                sequence=row.last_sequence,
                role="user",
                content=data.content,
                attachments=attachment_metadata,
                provider=None,
                created_at=now(),
            )
        )
        if row.automatic_title and row.last_sequence == 1:
            row.title = " ".join(data.content.split())[:60]
        row.updated_at = now()
        event(db, owner, "chat.question_submitted", request.id, trace)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "This request identifier cannot be used.") from None
        return Ticket(context)


def complete(
    engine: Engine,
    owner: UUID,
    sid: UUID,
    cid: UUID,
    request_id: UUID,
    answer: str | None,
    code: str | None,
    provider: str,
    trace: str,
    sources: list | None = None,
) -> TurnResult:
    with Session(engine, expire_on_commit=False) as db:
        row = owned(db, owner, cid, lock=True, include_deleted=True)
        request = db.get(ChatRequest, request_id)
        if not request or request.conversation_id != cid:
            raise HTTPException(404, "Question not found.")
        if row.deleted_at:
            if request.status == "pending":
                fail(request, "cancelled")
                db.commit()
            raise HTTPException(404, "Conversation not found.")
        try:
            live_identity(db, owner, sid)
        except HTTPException:
            if request.status == "pending":
                fail(request, "cancelled")
                db.commit()
            raise
        if request.status != "pending":
            return result(db, request, True)
        if utc(request.deadline_at) <= now():
            code = "interrupted"
        sources = sources or []
        for source in sorted(sources, key=lambda item: item["document_id"]):
            eligible = db.scalar(
                select(KnowledgeChunk.id)
                .join(KnowledgeDocument)
                .join(KnowledgeSubmission)
                .where(
                    KnowledgeChunk.id == UUID(source["chunk_id"]),
                    KnowledgeDocument.active.is_(True),
                    KnowledgeDocument.processing_status == "succeeded",
                    KnowledgeSubmission.status == "approved",
                    KnowledgeChunk.version == KnowledgeDocument.version,
                )
                .with_for_update(of=KnowledgeDocument)
            )
            if not eligible:
                code = "unavailable"
        if code:
            fail(request, code)
            event(db, owner, "chat.answer_failed", request.id, trace)
        else:
            row.last_sequence += 1
            db.add(
                Message(
                    conversation_id=cid,
                    request_id=request.id,
                    sequence=row.last_sequence,
                    role="assistant",
                    content=answer,
                    provider=provider,
                    created_at=now(),
                )
            )
            db.flush()
            message_id = db.scalar(
                select(Message.id).where(
                    Message.request_id == request.id, Message.role == "assistant"
                )
            )
            for source in sources:
                db.add(
                    MessageSource(
                        message_id=message_id,
                        document_id=UUID(source["document_id"]),
                        chunk_id=UUID(source["chunk_id"]),
                        label=source["id"],
                        title=source["title"],
                        location=source["location"],
                    )
                )
            request.status, request.completed_at = "succeeded", now()
            event(db, owner, "chat.answer_saved", request.id, trace)
        row.updated_at = now()
        db.commit()
        return result(db, request, False)


async def submit(
    engine: Engine,
    owner: UUID,
    sid: UUID,
    cid: UUID,
    data: TurnCreate,
    provider: AcademicProvider,
    config: Settings,
    trace: str,
    store=None,
) -> TurnResult:
    ticket = await run_in_threadpool(
        prepare, engine, owner, sid, cid, data, config, provider.available, trace, store
    )
    if ticket.cached is not None:
        return ticket.cached
    answer, code, sources = None, None, []
    try:
        answer = await asyncio.wait_for(
            provider.generate(ticket.context), config.chat_timeout_seconds
        )
        if not isinstance(answer, str) or not answer.strip():
            raise AcademicError("empty_response")
        if len(answer) > 12000:
            raise AcademicError("provider_failure")
        sources = getattr(answer, "sources", [])
        if sources:
            import re

            answer = re.sub(
                r"\[S(\d+)\]",
                lambda m: m.group() if int(m.group(1)) <= len(sources) else "",
                answer,
            )
            answer = (
                str(answer)
                + "\n\nReference materials retrieved:\n"
                + "\n".join(
                    f"- [{source['id']}] {source['title']} — {source['location']}"
                    for source in sources
                )
            )
        answer = answer.strip()
    except TimeoutError:
        code = "timeout"
    except AcademicError as exc:
        code = exc.code
    except Exception as exc:
        code = "provider_failure"
        logger.error(
            f"academic_provider_failed kind={type(exc).__name__}", extra={"request_id": trace}
        )
    return await run_in_threadpool(
        complete,
        engine,
        owner,
        sid,
        cid,
        data.request_id,
        answer,
        code,
        provider.mode,
        trace,
        sources,
    )
