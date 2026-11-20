"""Operator-authorized, versioned open-text excerpts. Never modifies model weights."""

import hashlib
import json
import logging
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.crypto import now
from app.knowledge.extract import chunk
from app.models.identity import AuditLog, User
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSubmission,
    ProcessingJob,
)

logger = logging.getLogger("edumind")


def load_sources():
    sources = []
    for path in sorted((Path(__file__).parent / "corpus").glob("*.json")):
        sources.extend(json.loads(path.read_text()))
    return sources


def install(engine, store, sources=None):
    """Idempotent import; existing/removed records are never reactivated."""
    installed = 0
    for source in load_sources() if sources is None else sources:
        sid = uuid5(NAMESPACE_URL, "edumind:starter:v1:" + source["id"])
        attribution = (
            f"{source['author']} — {source['license']} ({source['license_url']}). "
            f"Source: {source['url']}. {source['changes']}"
        )
        sections = source["sections"]
        chunks = chunk(sections, size=1350, overlap=150)
        if not chunks:
            raise ValueError("empty_starter_source")
        data = (attribution + "\n\n" + "\n\n".join(f"{a}\n{b}" for a, b in sections)).encode()
        key = f"knowledge/starter/{sid}.txt"
        with Session(engine) as db:
            if engine.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(72640193)"))
            if db.get(KnowledgeSubmission, sid):
                continue
            owner = db.scalar(
                select(User.id)
                .where(User.role == "admin", User.is_active.is_(True))
                .order_by(User.created_at)
                .limit(1)
            )
            if owner is None:
                raise ValueError("starter_requires_administrator")
            digest = hashlib.sha256(data).hexdigest()
            if db.scalar(
                select(KnowledgeSubmission.id).where(KnowledgeSubmission.digest == digest)
            ):
                continue
            store.put(key, data, "text/plain")
            submission = KnowledgeSubmission(
                id=sid,
                owner_id=owner,
                title=source["title"],
                description=attribution,
                discipline=source["discipline"],
                filename=source["id"] + ".txt",
                mime="text/plain",
                digest=digest,
                object_key=key,
                size=len(data),
                status="approved",
                reason="Operator-authorized licensed starter import; selected excerpts only.",
                created_at=now(),
            )
            db.add(submission)
            db.flush()
            doc = KnowledgeDocument(
                submission_id=sid,
                version=1,
                active=True,
                processing_status="succeeded",
                embedding_model="text-search-v1",
                metadata_json={
                    **{k: v for k, v in source.items() if k != "sections"},
                    "credit": attribution,
                },
                created_at=now(),
            )
            db.add(doc)
            db.flush()
            for ordinal, (location, content) in enumerate(chunks):
                db.add(
                    KnowledgeChunk(
                        document_id=doc.id,
                        version=1,
                        ordinal=ordinal,
                        location=location[:100],
                        content=content + "\n\n" + attribution,
                        embedding=None,
                    )
                )
            db.add(
                ProcessingJob(document_id=doc.id, state="succeeded", attempts=1, created_at=now())
            )
            db.add(
                AuditLog(
                    action="knowledge.open_starter_imported",
                    target_id=sid,
                    request_id="open-starter-v1",
                    created_at=now(),
                )
            )
            db.commit()
            installed += 1
            logger.info("knowledge_starter_imported source=%s chunks=%s", source["id"], len(chunks))
    logger.info("knowledge_starter_complete installed=%s", installed)
    return installed
