from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.crypto import now
from app.knowledge.extract import validate
from app.models.knowledge import KnowledgeDocument, KnowledgeSubmission, ProcessingJob
from app.services.identity import audit


def view(s, d=None):
    return {
        "id": str(s.id),
        "title": s.title,
        "description": s.description,
        "discipline": s.discipline,
        "filename": s.filename,
        "status": s.status,
        "reason": s.reason,
        "size": s.size,
        "created_at": s.created_at,
        "processing_status": d.processing_status if d else None,
        "active": d.active if d else False,
        "metadata": d.metadata_json if d else {},
    }


def submit(db, request, actor, title, description, discipline, filename, mime, data, store):
    if actor.role not in {"contributor", "admin"}:
        raise HTTPException(403, "Contributor approval required.")
    try:
        validate(filename, data, mime)
    except Exception:
        raise HTTPException(422, "Unsupported, invalid or oversized document.") from None
    digest = sha256(data).hexdigest()
    if db.scalar(select(KnowledgeSubmission.id).where(KnowledgeSubmission.digest == digest)):
        raise HTTPException(409, "Document already submitted.")
    key = "submissions/" + uuid4().hex
    row = KnowledgeSubmission(
        owner_id=actor.id,
        title=title,
        description=description,
        discipline=discipline,
        filename=filename,
        mime=mime,
        digest=digest,
        object_key=key,
        size=len(data),
        status="pending",
        created_at=now(),
    )
    try:
        store.put(key, data, mime)
    except Exception:
        raise HTTPException(503, "Document storage unavailable.") from None
    try:
        db.add(row)
        db.flush()
        audit(db, request, "knowledge.submitted", actor.id, row.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            store.delete(key)
        except Exception:
            pass
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "Document already submitted.") from None
        raise
    return view(row)


def review(db, request, actor, sid, decision, reason, model):
    s = db.scalar(
        select(KnowledgeSubmission).where(KnowledgeSubmission.id == sid).with_for_update()
    )
    if not s:
        raise HTTPException(404, "Submission not found.")
    if s.status != "pending":
        raise HTTPException(409, "Already reviewed.")
    s.status, s.reason, s.reviewer_id = (
        decision,
        reason if decision == "rejected" else None,
        actor.id,
    )
    if decision == "approved":
        d = KnowledgeDocument(submission_id=s.id, embedding_model=model, created_at=now())
        db.add(d)
        db.flush()
        db.add(ProcessingJob(document_id=d.id, created_at=now()))
    audit(db, request, "knowledge." + decision, actor.id, s.id)
    db.commit()
    return {"status": s.status}
