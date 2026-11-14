"""Gemini-independent, extractive search. This does not train model weights."""

import hashlib
import re
import unicodedata
from datetime import timedelta

from sqlalchemy import func, literal_column, select

from app.auth.crypto import now
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSubmission
from app.models.learning import LearningExample, LearningQuery

MAX_RANKED_MATCHES = 10_000


class KnowledgeQueryTooBroad(Exception):
    pass


def canonical(question):
    return " ".join(unicodedata.normalize("NFKC", question).casefold().split())


def question_digest(question):
    return hashlib.sha256(canonical(question).encode()).hexdigest()


def ranked(db, query, expression, question, tie_breaker):
    if db.bind.dialect.name == "postgresql":
        config = literal_column("'simple'")
        vector = func.to_tsvector(config, expression)
        terms = func.plainto_tsquery(config, question)
        matching = query.where(vector.op("@@")(terms))
        # Ranking computes a score for every match. Check the bound without sorting.
        overflow = (
            matching.with_only_columns(literal_column("1"), maintain_column_froms=True)
            .offset(MAX_RANKED_MATCHES)
            .limit(1)
        )
        if db.scalar(overflow) is not None:
            raise KnowledgeQueryTooBroad
        return list(
            db.execute(
                matching.order_by(func.ts_rank_cd(vector, terms).desc(), tie_breaker).limit(5)
            )
        )
    # SQLite is only used in isolated tests. Production uses indexed PostgreSQL FTS.
    terms = set(re.findall(r"\w+", canonical(question)))
    if not terms:
        return []
    candidates = list(db.execute(query.order_by(tie_breaker).limit(500)))
    return [
        row
        for row in candidates
        if terms.issubset(
            set(
                re.findall(
                    r"\w+",
                    canonical(
                        row.content if hasattr(row, "content") else row.question + " " + row.answer
                    ),
                )
            )
        )
    ][:5]


def search(db, question, *, match_title=False):
    examples = ranked(
        db,
        select(
            LearningExample.id,
            LearningExample.question,
            LearningExample.answer,
            LearningExample.evidence,
        ).where(LearningExample.status == "approved", LearningExample.split == "train"),
        LearningExample.question + literal_column("' '") + LearningExample.answer,
        question,
        LearningExample.id,
    )
    document_query = (
        select(
            KnowledgeChunk.id,
            KnowledgeSubmission.title,
            KnowledgeChunk.content,
            KnowledgeChunk.location,
            KnowledgeDocument.id.label("document_id"),
            KnowledgeDocument.metadata_json,
        )
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .join(KnowledgeSubmission, KnowledgeSubmission.id == KnowledgeDocument.submission_id)
        .where(
            KnowledgeSubmission.status == "approved",
            KnowledgeDocument.active.is_(True),
            KnowledgeDocument.processing_status == "succeeded",
            KnowledgeChunk.version == KnowledgeDocument.version,
        )
    )
    documents = ranked(db, document_query, KnowledgeChunk.content, question, KnowledgeChunk.id)
    if match_title and not documents:
        documents = list(
            db.execute(
                document_query.where(func.lower(KnowledgeSubmission.title) == canonical(question))
                .order_by(KnowledgeChunk.ordinal, KnowledgeChunk.id)
                .limit(3)
            )
        )
    sources = [
        {
            "kind": "reviewed_answer",
            "id": str(r.id),
            "title": r.question,
            "excerpt": r.answer[:1800],
            "location": r.evidence,
        }
        for r in examples
    ] + [
        {
            "kind": "document",
            "id": str(r.id),
            "document_id": str(r.document_id),
            "credit": (r.metadata_json or {}).get("credit", ""),
            "title": r.title,
            "excerpt": r.content[:1800],
            "location": r.location,
        }
        for r in documents
    ]
    return sources[:5]


def statistics(db):
    counts = {
        status: count
        for status, count in db.execute(
            select(LearningExample.status, func.count()).group_by(LearningExample.status)
        )
    }
    splits = {
        split: count
        for split, count in db.execute(
            select(LearningExample.split, func.count())
            .where(LearningExample.status == "approved")
            .group_by(LearningExample.split)
        )
    }
    corpus = (
        select(KnowledgeChunk.id)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .join(KnowledgeSubmission, KnowledgeSubmission.id == KnowledgeDocument.submission_id)
        .where(
            KnowledgeSubmission.status == "approved",
            KnowledgeDocument.active.is_(True),
            KnowledgeDocument.processing_status == "succeeded",
            KnowledgeChunk.version == KnowledgeDocument.version,
        )
    )
    measurements = list(
        db.scalars(
            select(LearningQuery)
            .where(LearningQuery.created_at >= now() - timedelta(days=7))
            .order_by(LearningQuery.created_at.desc())
            .limit(1000)
        )
    )
    durations = sorted(m.duration_ms for m in measurements)
    return {
        "examples": {k: counts.get(k, 0) for k in ("pending", "approved", "rejected")},
        "training_examples": splits.get("train", 0),
        "evaluation_examples": splits.get("evaluation", 0),
        "searchable_chunks": db.scalar(select(func.count()).select_from(corpus.subquery())),
        "queries": len(measurements),
        "queries_with_sources": sum(m.source_count > 0 for m in measurements),
        "p95_latency_ms": durations[max(0, (95 * len(durations) + 99) // 100 - 1)]
        if durations
        else None,
        "measurement_window": "Latest 1,000 completed searches within 7 days",
        "mode": "extractive_search",
        "gemini_replacement_ready": False,
        "gates": [
            {"name": "Reviewed training data", "status": "building"},
            {"name": "Held-out answer-quality evaluation", "status": "not_measured"},
            {"name": "Independent language model", "status": "not_configured"},
            {"name": "Token limits and concurrent-load testing", "status": "not_measured"},
        ],
    }
