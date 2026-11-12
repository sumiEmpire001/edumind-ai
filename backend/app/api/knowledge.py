from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.auth.crypto import now
from app.auth.dependencies import DB, Admin, Current, trusted_origin
from app.knowledge import service
from app.models.identity import User
from app.models.knowledge import (
    ContributorApplication,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSubmission,
    ProcessingJob,
)
from app.schemas.identity import InputModel
from app.security.rate_limit import consume
from app.services.identity import audit, revoke_sessions
from app.storage.objects import configured_store

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


class ApplicationInput(InputModel):
    statement: str = Field(min_length=20, max_length=2000)


class Decision(InputModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str = Field(default="", max_length=1000)


def valid_decision(data):
    if data.decision == "rejected" and not data.reason.strip():
        raise HTTPException(422, "A rejection reason is required.")


def application_view(a):
    return {
        "id": str(a.id),
        "user_id": str(a.user_id),
        "statement": a.statement,
        "status": a.status,
        "reason": a.reason,
        "created_at": a.created_at,
    }


@router.get("/contributor/application")
def my_application(db: DB, current: Current):
    row = db.scalar(
        select(ContributorApplication).where(ContributorApplication.user_id == current.user.id)
    )
    return application_view(row) if row else None


@router.post("/contributor/application", status_code=201, dependencies=[Depends(trusted_origin)])
def apply(data: ApplicationInput, request: Request, db: DB, current: Current):
    consume(request, "contributor-apply", str(current.user.id), 5, 3600)
    if current.user.role != "student":
        raise HTTPException(409, "Account already has contributor permissions.")
    db.scalar(select(User).where(User.id == current.user.id).with_for_update())
    if db.scalar(
        select(ContributorApplication).where(ContributorApplication.user_id == current.user.id)
    ):
        raise HTTPException(409, "An application already exists.")
    row = ContributorApplication(
        user_id=current.user.id, statement=data.statement, created_at=now()
    )
    db.add(row)
    audit(db, request, "contributor.applied", current.user.id)
    db.commit()
    return application_view(row)


@router.get("/admin/contributor-applications")
def applications(db: DB, admin: Admin, offset: int = Query(0, ge=0)):
    return [
        application_view(a)
        for a in db.scalars(
            select(ContributorApplication)
            .order_by(ContributorApplication.created_at.desc())
            .offset(offset)
            .limit(50)
        )
    ]


@router.post("/admin/contributor-applications/{aid}/review", dependencies=[Depends(trusted_origin)])
def review_application(aid: UUID, data: Decision, request: Request, db: DB, admin: Admin):
    valid_decision(data)
    row = db.scalar(
        select(ContributorApplication).where(ContributorApplication.id == aid).with_for_update()
    )
    if not row:
        raise HTTPException(404, "Application not found.")
    if row.status != "pending":
        raise HTTPException(409, "Already reviewed.")
    user = db.scalar(select(User).where(User.id == row.user_id).with_for_update())
    if not user.is_active or user.role != "student":
        raise HTTPException(409, "Account is not eligible.")
    row.status, row.reason = data.decision, data.reason
    if data.decision == "approved":
        user.role, user.updated_at = "contributor", now()
        revoke_sessions(db, user.id)
    audit(db, request, "contributor." + data.decision, admin.user.id, row.user_id)
    db.commit()
    return application_view(row)


@router.get("/knowledge/submissions")
def submissions(db: DB, current: Current, offset: int = Query(0, ge=0)):
    q = select(KnowledgeSubmission, KnowledgeDocument).outerjoin(
        KnowledgeDocument, KnowledgeDocument.submission_id == KnowledgeSubmission.id
    )
    if current.user.role != "admin":
        q = q.where(KnowledgeSubmission.owner_id == current.user.id)
    return [
        service.view(s, d)
        for s, d in db.execute(
            q.order_by(KnowledgeSubmission.created_at.desc()).offset(offset).limit(50)
        )
    ]


@router.post("/knowledge/submissions", status_code=201, dependencies=[Depends(trusted_origin)])
async def upload(
    request: Request,
    db: DB,
    current: Current,
    title: str = Query(min_length=1, max_length=200),
    filename: str = Query(min_length=1, max_length=200),
    description: str = Query(default="", max_length=2000),
    discipline: str = Query(default="", max_length=100),
):
    consume(request, "knowledge-upload", str(current.user.id), 10, 3600)
    if current.user.role not in {"contributor", "admin"}:
        raise HTTPException(403, "Contributor access required.")
    data = await request.body()
    store = getattr(request.app.state, "object_store", None) or configured_store(
        request.app.state.settings
    )
    return await run_in_threadpool(
        service.submit,
        db,
        request,
        current.user,
        title,
        description,
        discipline,
        filename,
        request.headers.get("content-type", "").split(";")[0],
        data,
        store,
    )


@router.get("/knowledge/submissions/{sid}/preview")
def preview(sid: UUID, request: Request, db: DB, current: Current):
    row = db.get(KnowledgeSubmission, sid)
    if not row or (current.user.role != "admin" and row.owner_id != current.user.id):
        raise HTTPException(404, "Submission not found.")
    store = getattr(request.app.state, "object_store", None) or configured_store(
        request.app.state.settings
    )
    try:
        data = store.get(row.object_key)
    except Exception:
        raise HTTPException(503, "Preview unavailable.") from None
    mime = (
        row.mime
        if row.mime in {"application/pdf", "text/plain", "text/csv"}
        else "application/octet-stream"
    )
    return Response(
        data,
        media_type=mime,
        headers={
            "Content-Disposition": 'inline; filename="document"',
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/admin/submissions/{sid}/review", dependencies=[Depends(trusted_origin)])
def review(sid: UUID, data: Decision, request: Request, db: DB, admin: Admin):
    valid_decision(data)
    consume(request, "knowledge-review", str(admin.user.id), 60, 60)
    return service.review(
        db,
        request,
        admin.user,
        sid,
        data.decision,
        data.reason,
        request.app.state.settings.embedding_model,
    )


@router.get("/admin/knowledge")
def knowledge(db: DB, admin: Admin, offset: int = Query(0, ge=0)):
    rows = db.execute(
        select(KnowledgeDocument, ProcessingJob.error_code, KnowledgeSubmission.mime)
        .join(KnowledgeSubmission, KnowledgeDocument.submission_id == KnowledgeSubmission.id)
        .outerjoin(ProcessingJob, ProcessingJob.document_id == KnowledgeDocument.id)
        .order_by(KnowledgeDocument.created_at.desc())
        .offset(offset)
        .limit(50)
    )
    return [
        {
            "id": str(d.id),
            "submission_id": str(d.submission_id),
            "version": d.version,
            "active": d.active,
            "processing_status": d.processing_status,
            "embedding_model": d.embedding_model,
            "mime": mime,
            "metadata": {k: v for k, v in d.metadata_json.items() if k != "handwriting_pages"},
            "error_code": error_code,
        }
        for d, error_code, mime in rows
    ]


@router.post("/admin/knowledge/{did}/reindex", dependencies=[Depends(trusted_origin)])
def reindex(did: UUID, request: Request, db: DB, admin: Admin):
    d = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == did).with_for_update())
    if not d:
        raise HTTPException(404, "Document not found.")
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == did).with_for_update())
    if job.state in {"queued", "processing"}:
        raise HTTPException(409, "Already queued or processing.")
    d.active, d.processing_status = False, "queued"
    job.state, job.attempts, job.error_code = "queued", 0, None
    audit(db, request, "knowledge.reindex", admin.user.id, did)
    db.commit()
    return {"status": "queued"}


@router.delete("/admin/knowledge/{did}", dependencies=[Depends(trusted_origin)])
def deactivate(did: UUID, request: Request, db: DB, admin: Admin):
    d = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == did).with_for_update())
    if not d:
        raise HTTPException(404, "Document not found.")
    d.active, d.processing_status = False, "failed"
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == did).with_for_update())
    job.state, job.lease_until, job.error_code = "failed", None, "removed_by_admin"
    audit(db, request, "knowledge.removed", admin.user.id, did)
    db.commit()
    return {"status": "removed"}


@router.get("/admin/statistics")
def statistics(db: DB, admin: Admin):
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "submissions": db.scalar(select(func.count()).select_from(KnowledgeSubmission)),
        "active_documents": db.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.active.is_(True))
        ),
        "jobs": [
            {"state": s, "count": n}
            for s, n in db.execute(
                select(ProcessingJob.state, func.count()).group_by(ProcessingJob.state)
            )
        ],
    }


@router.get("/knowledge/submissions/{sid}/preview-data")
def preview_data(sid: UUID, request: Request, db: DB, current: Current):
    from app.knowledge.extract import extract

    response = preview(sid, request, db, current)
    row = db.get(KnowledgeSubmission, sid)
    document = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.submission_id == sid,
            KnowledgeDocument.processing_status == "succeeded",
            KnowledgeDocument.active.is_(True),
        )
    )
    if document:
        passages = db.scalars(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.version == document.version,
            )
            .order_by(KnowledgeChunk.ordinal)
        ).all()
        return {
            "text": "\n\n".join(c.location + "\n" + c.content for c in passages)[:100000],
            "metadata": document.metadata_json,
        }
    try:
        sections, metadata = extract(row.filename, response.body, row.mime)
    except Exception:
        raise HTTPException(
            422,
            "No native text preview available. Scanned PDFs are transcribed after "
            "approval; review the original file first.",
        ) from None
    return {
        "text": "\n\n".join(location + "\n" + text for location, text in sections)[:100000],
        "metadata": metadata,
    }


@router.get("/knowledge/capabilities")
def knowledge_capabilities(request: Request, current: Current):
    config = request.app.state.settings
    available = bool(
        (config.blob_store_id and config.blob_read_write_token)
        or (config.storage_bucket and config.storage_access_key and config.storage_secret_key)
    )
    available = available or (
        config.app_env == "test" and hasattr(request.app.state, "object_store")
    )
    return {
        "storage_available": available,
        "max_upload_bytes": 3 * 1024 * 1024,
        "rag_enabled": config.rag_enabled,
    }


class TranscriptionPage(InputModel):
    page: int = Field(ge=1, le=10, strict=True)
    text: str = Field(max_length=20000)


class TranscriptionReview(InputModel):
    version: int = Field(ge=1, strict=True)
    pages: list[TranscriptionPage] = Field(min_length=1, max_length=10)


def handwriting_document(db, did):
    document = db.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.id == did).with_for_update()
    )
    if not document:
        raise HTTPException(404, "Document not found.")
    submission = db.get(KnowledgeSubmission, document.submission_id)
    if submission.status != "approved" or submission.mime != "application/pdf":
        raise HTTPException(409, "Approve a PDF before requesting handwriting transcription.")
    return document


@router.post("/admin/knowledge/{did}/handwriting", dependencies=[Depends(trusted_origin)])
def queue_handwriting(did: UUID, request: Request, db: DB, admin: Admin):
    consume(request, "handwriting", str(admin.user.id), 5, 3600)
    if not request.app.state.settings.gemini_api_key:
        raise HTTPException(503, "Gemini vision is not configured.")
    document = handwriting_document(db, did)
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == did).with_for_update())
    if job.state in {"queued", "processing"}:
        raise HTTPException(409, "Processing is already running.")
    document.metadata_json = {"extraction_mode": "handwriting"}
    document.active, document.processing_status = False, "queued"
    job.state, job.attempts, job.error_code, job.lease_until = "queued", 0, None, None
    audit(db, request, "knowledge.handwriting_requested", admin.user.id, did)
    db.commit()
    return {"status": "queued"}


@router.get("/admin/knowledge/{did}/handwriting")
def handwriting_preview(did: UUID, request: Request, db: DB, admin: Admin):
    document = handwriting_document(db, did)
    if not document.metadata_json.get("handwriting_review_required"):
        raise HTTPException(409, "No handwriting draft awaiting review.")
    import base64

    submission = db.get(KnowledgeSubmission, document.submission_id)
    store = getattr(request.app.state, "object_store", None) or configured_store(
        request.app.state.settings
    )
    try:
        original = store.get(submission.object_key)
        if len(original) > 3 * 1024 * 1024 or not original.startswith(b"%PDF-"):
            raise ValueError("invalid_original")
    except Exception:
        raise HTTPException(503, "Original PDF unavailable; try again before reviewing.") from None
    return {
        "version": document.version,
        "pages": document.metadata_json["handwriting_pages"],
        "original_pdf_base64": base64.b64encode(original).decode(),
    }


@router.post("/admin/knowledge/{did}/handwriting/approve", dependencies=[Depends(trusted_origin)])
def approve_handwriting(
    did: UUID, data: TranscriptionReview, request: Request, db: DB, admin: Admin
):
    from app.knowledge.extract import chunk

    consume(request, "handwriting-review", str(admin.user.id), 30, 60)
    document = handwriting_document(db, did)
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == did).with_for_update())
    metadata = document.metadata_json
    if (
        document.version != data.version
        or document.processing_status != "succeeded"
        or job.state != "succeeded"
        or not metadata.get("handwriting_review_required")
    ):
        raise HTTPException(409, "The draft changed. Reload it before approving.")
    if [p.page for p in data.pages] != list(range(1, metadata["page_count"] + 1)):
        raise HTTPException(422, "Keep every page in its original order.")
    if any("[unclear]" in p.text.lower() or "\x00" in p.text for p in data.pages):
        raise HTTPException(
            422, "Resolve all [unclear] markers using the original before approval."
        )
    if not any(p.text.strip() for p in data.pages) or sum(len(p.text) for p in data.pages) > 100000:
        raise HTTPException(422, "Provide readable text within 100,000 characters.")
    sections = [(f"Page {p.page} (reviewed transcription)", p.text.strip()) for p in data.pages]
    try:
        pieces = chunk(sections)
    except ValueError:
        raise HTTPException(422, "The transcription is too large.") from None
    version = document.version + 1
    for ordinal, (location, content) in enumerate(pieces):
        db.add(
            KnowledgeChunk(
                document_id=did,
                version=version,
                ordinal=ordinal,
                location=location,
                content=content,
                embedding=None,
            )
        )
    document.version, document.active = version, True
    document.metadata_json = {
        **metadata,
        "handwriting_review_required": False,
        "handwriting_pages": [p.model_dump() for p in data.pages],
        "transcription_reviewed_by": str(admin.user.id),
        "transcription_reviewed_at": now().isoformat(),
    }
    audit(db, request, "knowledge.transcription_approved", admin.user.id, did)
    db.commit()
    return {"status": "searchable", "version": version}
