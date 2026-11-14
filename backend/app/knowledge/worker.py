"""Durable PostgreSQL job worker. Run separately: python -m app.knowledge.worker."""

import argparse
import logging
import os
import signal
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.crypto import now
from app.core.config import get_settings
from app.database.session import build_engine
from app.knowledge.extract import chunk, extract
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSubmission,
    ProcessingJob,
)
from app.storage.objects import configured_store

logger = logging.getLogger("edumind")


def run_one(engine, store, embeddings, settings=None):
    with Session(engine) as db:
        exhausted = list(
            db.execute(
                select(
                    ProcessingJob.id, ProcessingJob.document_id, ProcessingJob.lease_until
                ).where(
                    ProcessingJob.state == "processing",
                    ProcessingJob.attempts >= 3,
                    ProcessingJob.lease_until < now(),
                )
            )
        )
    for jid, did, lease in exhausted:
        fail(engine, jid, did, lease, "attempts_exhausted")
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
        handwriting = d.metadata_json.get("extraction_mode") == "handwriting"
    try:
        if handwriting:
            from app.knowledge.handwriting import extract_handwriting

            sections, metadata = extract_handwriting(store.get(key), settings or get_settings())
        else:
            data = store.get(key)
            vision_available = mime == "application/pdf" and settings and settings.gemini_api_key
            try:
                sections, metadata = extract(filename, data, mime, allow_ocr=True)
            except ValueError as exc:
                if not vision_available or str(exc) not in {
                    "ocr_review_required",
                    "no_text_ocr_required",
                }:
                    raise
                from app.knowledge.handwriting import extract_handwriting

                sections, metadata = extract_handwriting(data, settings)
            else:
                # Handwriting can look confidently wrong to printed-text OCR. Let vision
                # transcribe detected scan pages even when local OCR did not reject them.
                if (
                    vision_available
                    and metadata.get("ocr_pages")
                    and metadata.get("page_count", 0) <= 10
                ):
                    from app.knowledge.handwriting import extract_handwriting

                    sections, metadata = extract_handwriting(data, settings)
        chunks = chunk(sections)
        if embeddings is not None and embeddings.model != model:
            raise ValueError("embedding_model_changed")
        vectors = (
            embeddings.embed([text for _, text in chunks])
            if embeddings is not None and not metadata.get("handwriting_review_required")
            else [None] * len(chunks)
        )
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
                not metadata.get("handwriting_review_required", False),
                "succeeded",
                metadata,
            )
            j.state, j.lease_until, j.error_code = "succeeded", None, None
            db.commit()
        logger.info(
            "knowledge_document_indexed document_id=%s chunks=%s mode=%s",
            did,
            len(chunks),
            "text" if embeddings is None else "semantic",
        )
    except Exception as exc:
        # Parser/provider exceptions never include document content or credentials in logs.
        logger.error(
            "knowledge_processing_failed document_id=%s kind=%s sqlstate=%s",
            did,
            type(exc).__name__,
            getattr(getattr(exc, "orig", None), "sqlstate", None),
        )
        code = "text_processing_failed" if embeddings is None else "processing_failed"
        if isinstance(exc, ValueError) and str(exc) in {
            "ocr_review_required",
            "ocr_page_limit",
            "ocr_timeout",
            "ocr_unavailable",
            "ocr_output_limit",
            "handwriting_unavailable",
            "handwriting_quota",
            "handwriting_incomplete",
            "handwriting_page_limit",
            "handwriting_timeout",
            "handwriting_render_failed",
            "handwriting_empty",
            "handwriting_text_limit",
        }:
            code = str(exc)
        logger.warning("knowledge_processing_error document_id=%s code=%s", did, code)
        fail(engine, jid, did, lease, code)
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


def retry_for_text_indexing(engine):
    """Give legacy processing failures one keyword-only attempt."""
    with Session(engine) as db:
        candidates = list(
            db.scalars(
                select(ProcessingJob.document_id).where(
                    ProcessingJob.state == "failed",
                    ProcessingJob.error_code == "processing_failed",
                )
            )
        )
        for did in candidates:
            document = db.scalar(
                select(KnowledgeDocument).where(KnowledgeDocument.id == did).with_for_update()
            )
            job = db.scalar(
                select(ProcessingJob).where(ProcessingJob.document_id == did).with_for_update()
            )
            if job.state != "failed" or job.error_code != "processing_failed":
                continue
            submission = db.get(KnowledgeSubmission, document.submission_id)
            if submission.status == "approved":
                job.state, job.attempts, job.error_code = "queued", 0, None
                document.processing_status = "queued"
        db.commit()


def retry_failed_scans(engine, settings):
    """One recovery attempt per approved failed PDF; never revive removed documents."""
    if not settings.gemini_api_key:
        return
    recoverable = {"ocr_review_required", "no_text_ocr_required", "text_processing_failed"}
    with Session(engine) as db:
        ids = list(
            db.scalars(
                select(ProcessingJob.document_id).where(
                    ProcessingJob.state == "failed", ProcessingJob.error_code.in_(recoverable)
                )
            )
        )
        for did in ids:
            document = db.scalar(
                select(KnowledgeDocument).where(KnowledgeDocument.id == did).with_for_update()
            )
            job = db.scalar(
                select(ProcessingJob).where(ProcessingJob.document_id == did).with_for_update()
            )
            submission = db.get(KnowledgeSubmission, document.submission_id)
            if (
                job.state != "failed"
                or job.error_code not in recoverable
                or submission.status != "approved"
                or submission.mime != "application/pdf"
                or document.metadata_json.get("automatic_vision_attempted")
            ):
                continue
            document.metadata_json = {
                **document.metadata_json,
                "extraction_mode": "handwriting",
                "automatic_vision_attempted": True,
            }
            document.active, document.processing_status = False, "queued"
            job.state, job.attempts, job.error_code, job.lease_until = "queued", 0, None, None
        db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-only", action="store_true")
    text_only = parser.parse_args().text_only
    config = get_settings()
    from app.core.logging import configure_logging

    configure_logging(config.log_level)
    if text_only:
        # The hosted parser runs in its own low-priority process on the Linux service.
        import resource

        os.nice(10)
        limit = 256 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        embedder = None
    else:
        from app.knowledge.embeddings import Embeddings

        embedder = Embeddings(config)
    store = configured_store(config)
    engine = build_engine(config)
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        recover = text_only
        while running:
            try:
                if recover:
                    if os.environ.get("KNOWLEDGE_STARTER_ENABLED") == "true":
                        from app.knowledge.starter import install

                        try:
                            install(engine, store)
                        except Exception as exc:
                            logger.warning("knowledge_starter_failed kind=%s", type(exc).__name__)
                    retry_for_text_indexing(engine)
                    retry_failed_scans(engine, config)
                    recover = False
                processed = run_one(engine, store, embedder, config)
            except SQLAlchemyError as exc:
                logger.warning("knowledge_queue_unavailable kind=%s", type(exc).__name__)
                processed = False
            if not processed:
                time.sleep(5 if text_only else 2)
    finally:
        if embedder is not None:
            embedder.close()
        engine.dispose()


if __name__ == "__main__":
    main()
