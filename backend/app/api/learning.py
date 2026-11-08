import hashlib
import json
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.crypto import now
from app.auth.dependencies import DB, Admin, Current, trusted_origin
from app.knowledge.learning import question_digest, search, statistics
from app.models.learning import LearningExample, LearningQuery
from app.schemas.identity import InputModel
from app.security.rate_limit import consume
from app.services.identity import audit

router = APIRouter(prefix="/api/v1", tags=["learning"])


class Question(InputModel):
    question: str = Field(min_length=5, max_length=2000)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value):
        value = value.strip()
        if len(value) < 5 or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("A readable question is required")
        return value


class Nomination(Question):
    consent_to_share: Literal[True]


class Review(InputModel):
    status: Literal["approved", "rejected"]
    answer: str = Field(default="", max_length=12000)
    evidence: str = Field(default="", max_length=2000)
    split: Literal["train", "evaluation"] = "train"
    rights_confirmed: bool = False


def view(row):
    return {
        "id": str(row.id),
        "question": row.question,
        "answer": row.answer,
        "evidence": row.evidence,
        "status": row.status,
        "split": row.split,
        "reviewed": row.reviewer_id is not None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.post("/learning/examples", status_code=201, dependencies=[Depends(trusted_origin)])
def nominate(data: Nomination, request: Request, db: DB, current: Current):
    consume(request, "learning-nominate", str(current.user.id), 10, 3600)
    row = LearningExample(
        owner_id=current.user.id,
        question=data.question,
        question_digest=question_digest(data.question),
        created_at=now(),
        updated_at=now(),
    )
    db.add(row)
    audit(db, request, "learning.nominated", current.user.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Do not reveal another user's question or owner.
        raise HTTPException(409, "This question is already in the review process.") from None
    return view(row)


@router.get("/learning/examples")
def examples(db: DB, current: Current, offset: int = Query(0, ge=0)):
    q = select(LearningExample)
    if current.user.role != "admin":
        q = q.where(LearningExample.owner_id == current.user.id)
    return [
        view(row)
        for row in db.scalars(
            q.order_by(LearningExample.created_at.desc(), LearningExample.id)
            .offset(offset)
            .limit(50)
        )
    ]


@router.post("/admin/learning/examples/{eid}/review", dependencies=[Depends(trusted_origin)])
def review(eid: UUID, data: Review, request: Request, db: DB, admin: Admin):
    consume(request, "learning-review", str(admin.user.id), 60, 60)
    if data.status == "approved" and (
        len(data.answer.strip()) < 20 or not data.evidence.strip() or not data.rights_confirmed
    ):
        raise HTTPException(422, "Verify the answer, evidence and reuse rights before approval.")
    row = db.scalar(select(LearningExample).where(LearningExample.id == eid).with_for_update())
    if not row:
        raise HTTPException(404, "Example not found.")
    # A held-out example cannot later enter the training corpus via the UI.
    if row.reviewer_id is not None and row.split != data.split:
        raise HTTPException(409, "Approved dataset splits are immutable.")
    row.status, row.answer = data.status, data.answer.strip()
    row.evidence, row.split = data.evidence.strip(), data.split
    row.reviewer_id, row.updated_at = admin.user.id, now()
    audit(db, request, "learning." + data.status, admin.user.id, row.id)
    db.commit()
    return view(row)


@router.post("/learning/query", dependencies=[Depends(trusted_origin)])
def query(data: Question, request: Request, db: DB, current: Current):
    consume(request, "learning-query", str(current.user.id), 30, 60)
    started = time.perf_counter()
    sources = search(db, data.question)
    elapsed = max(0, round((time.perf_counter() - started) * 1000))
    # No raw query text, user ID, attachments or private conversation content in telemetry.
    db.add(LearningQuery(duration_ms=elapsed, source_count=len(sources), created_at=now()))
    db.commit()
    return {
        "mode": "extractive_search",
        "uses_gemini": False,
        "status": "sources_found" if sources else "insufficient_knowledge",
        "sources": sources,
        "duration_ms": elapsed,
        "message": "Relevant approved excerpts; verify they answer your question."
        if sources
        else "No matching approved knowledge. Try Study chat or a different question.",
    }


@router.get("/admin/learning/overview")
def overview(db: DB, admin: Admin):
    return statistics(db)


@router.get("/admin/learning/dataset")
def dataset(
    request: Request,
    db: DB,
    admin: Admin,
    split: Literal["train", "evaluation"] = "train",
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    consume(request, "learning-export", str(admin.user.id), 10, 60)
    criteria = (LearningExample.status == "approved", LearningExample.split == split)
    rows = list(
        db.scalars(
            select(LearningExample)
            .where(*criteria)
            .order_by(LearningExample.created_at, LearningExample.id)
            .offset(offset)
            .limit(limit)
        )
    )
    records = [
        {
            "messages": [
                {"role": "user", "content": r.question},
                {"role": "assistant", "content": r.answer},
            ]
        }
        for r in rows
    ]
    jsonl = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    total = db.scalar(select(func.count()).select_from(LearningExample).where(*criteria))
    audit(db, request, "learning.dataset_exported", admin.user.id)
    db.commit()
    return {
        "format": "messages-jsonl",
        "split": split,
        "count": len(records),
        "total": total,
        "offset": offset,
        "next_offset": offset + len(records) if offset + len(records) < total else None,
        "sha256": hashlib.sha256(jsonl.encode()).hexdigest(),
        "jsonl": jsonl,
        "notice": "Reviewed examples only. No documents or private conversations included. "
        "Keep evaluation data separate from training. Page hash covers this download.",
    }
