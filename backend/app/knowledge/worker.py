"""Durable PostgreSQL job worker. Run separately: python -m app.knowledge.worker."""

import logging
import signal
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.crypto import now
from app.core.config import get_settings
from app.database.session import build_engine
from app.knowledge.embeddings import Embeddings
from app.knowledge.extract import chunk, extract
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSubmission,
    ProcessingJob,
)
from app.storage.objects import configured_store

logger = logging.getLogger("edumind")


def run_one(engine, store, embeddings):
    with Session(engine) as db:
        job = db.scalar(
            select(ProcessingJob)
            .where(
                or_(
                    ProcessingJob.state == "queued",
                    (ProcessingJob.state == "processing") & (ProcessingJob.lease_until < now()),
                ),
                ProcessingJob.attempts < 3,
            )
            .order_by(ProcessingJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job.state, job.attempts = "processing", job.attempts + 1
        lease = now() + timedelta(minutes=10)
        job.lease_until = lease
        jid, did, attempt = job.id, job.document_id, job.attempts
        db.commit()
        d = db.get(KnowledgeDocument, did)
        s = db.get(KnowledgeSubmission, d.submission_id)
        if s.status != "approved":
            return fail(engine, jid, did, lease, "approval_required")
        d.processing_status = "processing"
        db.commit()
        filename, mime, key = s.filename, s.mime, s.object_key
        model = d.embedding_model
    try:
        sections, metadata = extract(filename, store.get(key), mime)
        chunks = chunk(sections)
        if embeddings.model != model:
            raise ValueError("embedding_model_changed")
        vectors = embeddings.embed([text for _, text in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("invalid_embeddings")
        with Session(engine) as db:
            d = db.scalar(
                select(KnowledgeDocument).where(KnowledgeDocument.id == did).with_for_update()
            )
            j = db.scalar(select(ProcessingJob).where(ProcessingJob.id == jid).with_for_update())
            s = db.get(KnowledgeSubmission, d.submission_id)
            if (
                j.state != "processing"
                or j.attempts != attempt
                or j.lease_until.replace(tzinfo=lease.tzinfo) != lease
                or s.status != "approved"
            ):
                return True
            version = d.version + 1
            for ordinal, ((location, content), vector) in enumerate(
                zip(chunks, vectors, strict=True)
            ):
                db.add(
                    KnowledgeChunk(
                        id=uuid4(),
                        document_id=did,
                        version=version,
                        ordinal=ordinal,
                        location=location,
                        content=content,
                        embedding=vector,
                    )
                )
            d.version, d.active, d.processing_status, d.metadata_json = (
                version,
                True,
                "succeeded",
                metadata,
            )
            j.state, j.lease_until, j.error_code = "succeeded", None, None
            db.commit()
    except Exception as exc:
        # Parser/provider exceptions never include document content or credentials in logs.
        logger.error("knowledge_processing_failed kind=%s", type(exc).__name__)
        fail(engine, jid, did, lease, "processing_failed")
    return True


def fail(engine, jid, did, lease, code):
    with Session(engine) as db:
        d = db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.id == did).with_for_update()
        )
        j = db.scalar(select(ProcessingJob).where(ProcessingJob.id == jid).with_for_update())
        if (
            j.state == "processing"
            and j.lease_until
            and j.lease_until.replace(tzinfo=lease.tzinfo) == lease
        ):
            j.state, j.error_code, j.lease_until = "failed", code, None
            d.active, d.processing_status = False, "failed"
            db.commit()
    return True


def main():
    config = get_settings()
    engine, store, embedder = build_engine(config), configured_store(config), Embeddings(config)
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while running:
            if not run_one(engine, store, embedder):
                time.sleep(2)
    finally:
        embedder.close()
        engine.dispose()


if __name__ == "__main__":
    main()
