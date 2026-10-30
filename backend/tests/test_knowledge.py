from types import SimpleNamespace
from uuid import UUID
from zipfile import BadZipFile

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.extract import chunk, extract, validate
from app.knowledge.retrieval import eligible_query
from app.knowledge.worker import run_one
from app.models.identity import User
from app.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    ProcessingJob,
)
from tests.test_auth import api as api
from tests.test_auth import auth, login, register
from tests.test_auth import engine as engine


class MemoryStore:
    def __init__(self):
        self.data = {}

    def put(self, key, data, mime):
        self.data[key] = data

    def get(self, key):
        return self.data[key]

    def delete(self, key):
        self.data.pop(key, None)


class FakeEmbeddings:
    model = "gemini-embedding-001"

    def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
        return [[1.0] + [0.0] * 767 for _ in texts]


@pytest.fixture
def knowledge(api):
    client, engine, settings = api
    uid = UUID(register(client).json()["id"])
    with Session(engine) as db:
        user = db.get(User, uid)
        user.role = "contributor"
        db.commit()
    contributor = auth(login(client))
    admin_id = UUID(register(client, email="admin@example.com").json()["id"])
    with Session(engine) as db:
        db.get(User, admin_id).role = "admin"
        db.commit()
    admin = auth(login(client, email="admin@example.com"))
    store = MemoryStore()
    client.app.state.object_store = store
    return SimpleNamespace(
        client=client,
        engine=engine,
        settings=settings,
        contributor=contributor,
        admin=admin,
        store=store,
        uid=uid,
    )


def upload(k, content=b"Force equals mass times acceleration.", headers=None):
    return k.client.post(
        "/api/v1/knowledge/submissions?title=Mechanics&filename=lesson.txt&discipline=Physics",
        headers={**(headers or k.contributor), "Content-Type": "text/plain"},
        content=content,
    )


def approve(k, sid):
    return k.client.post(
        f"/api/v1/admin/submissions/{sid}/review", headers=k.admin, json={"decision": "approved"}
    )


def test_pending_approval_processing_boundary(knowledge):
    k = knowledge
    r = upload(k)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["status"] == "pending"
    assert not run_one(k.engine, k.store, FakeEmbeddings())
    with Session(k.engine) as db:
        assert not list(db.execute(eligible_query(FakeEmbeddings.model)))
    assert approve(k, sid).status_code == 200
    with Session(k.engine) as db:
        d = db.scalar(select(KnowledgeDocument))
        assert not d.active and d.processing_status == "queued"
    assert run_one(k.engine, k.store, FakeEmbeddings())
    with Session(k.engine) as db:
        assert len(list(db.execute(eligible_query(FakeEmbeddings.model)))) == 1
        d = db.scalar(select(KnowledgeDocument))
        assert d.active and d.version == 1
        did = str(d.id)
    assert k.client.delete(f"/api/v1/admin/knowledge/{did}", headers=k.admin).status_code == 200
    with Session(k.engine) as db:
        assert not list(db.execute(eligible_query(FakeEmbeddings.model)))


def test_rejection_duplicate_and_permissions(knowledge):
    k = knowledge
    sid = upload(k).json()["id"]
    assert upload(k).status_code == 409
    endpoint = f"/api/v1/admin/submissions/{sid}/review"
    assert (
        k.client.post(endpoint, headers=k.contributor, json={"decision": "approved"}).status_code
        == 403
    )
    assert (
        k.client.post(endpoint, headers=k.admin, json={"decision": "rejected"}).status_code == 422
    )
    assert (
        k.client.post(
            endpoint, headers=k.admin, json={"decision": "rejected", "reason": "Incorrect formula"}
        ).status_code
        == 200
    )
    assert not run_one(k.engine, k.store, FakeEmbeddings())
    assert approve(k, sid).status_code == 409
    assert (
        k.client.get("/api/v1/knowledge/submissions", headers=k.contributor).json()[0]["reason"]
        == "Incorrect formula"
    )


def test_processing_failure_and_reindex(knowledge):
    k = knowledge
    sid = upload(k).json()["id"]
    approve(k, sid)

    class Broken(FakeEmbeddings):
        def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
            raise RuntimeError("provider key should never reach logs")

    assert run_one(k.engine, k.store, Broken())
    with Session(k.engine) as db:
        d = db.scalar(select(KnowledgeDocument))
        assert d.processing_status == "failed" and not d.active
        did = str(d.id)
    assert (
        k.client.post(f"/api/v1/admin/knowledge/{did}/reindex", headers=k.admin).status_code == 200
    )
    assert run_one(k.engine, k.store, FakeEmbeddings())


def test_preview_owner_isolation(knowledge):
    k = knowledge
    sid = upload(k).json()["id"]
    assert k.client.get(
        f"/api/v1/knowledge/submissions/{sid}/preview", headers=k.admin
    ).content.startswith(b"Force")
    register(k.client, email="outsider@example.com")
    other = auth(login(k.client, email="outsider@example.com"))
    assert (
        k.client.get(f"/api/v1/knowledge/submissions/{sid}/preview", headers=other).status_code
        == 404
    )
    assert upload(k, headers=other).status_code == 403
    assert k.client.get("/api/v1/admin/statistics", headers=other).status_code == 403


def test_application_requires_admin(knowledge):
    k = knowledge
    register(k.client, email="new@example.com")
    student = auth(login(k.client, email="new@example.com"))
    r = k.client.post(
        "/api/v1/contributor/application",
        headers=student,
        json={"statement": "I can contribute verified physics learning materials."},
    )
    assert r.status_code == 201
    aid = r.json()["id"]
    assert (
        k.client.post(
            f"/api/v1/admin/contributor-applications/{aid}/review",
            headers=student,
            json={"decision": "approved"},
        ).status_code
        == 403
    )
    assert (
        k.client.post(
            f"/api/v1/admin/contributor-applications/{aid}/review",
            headers=k.admin,
            json={"decision": "approved"},
        ).status_code
        == 200
    )
    with Session(k.engine) as db:
        assert db.scalar(select(User).where(User.email == "new@example.com")).role == "contributor"
    assert k.client.get("/api/v1/users/me", headers=student).status_code == 401


@pytest.mark.parametrize(
    "name,data,mime",
    [
        ("fake.pdf", b"not pdf", "application/pdf"),
        ("bad.exe", b"text", "text/plain"),
        ("file.txt", b"x", "application/pdf"),
        ("file.txt", b"\x00", "text/plain"),
        (
            "file.docx",
            b"PKinvalid",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_invalid_files(name, data, mime):
    with pytest.raises((ValueError, BadZipFile)):
        validate(name, data, mime)


def test_extraction_and_bounded_chunks():
    sections, metadata = extract("a.csv", b"mass,force\n2,10", "text/csv")
    assert "2 | 10" in sections[0][1]
    assert metadata == {"file_type": "csv"}
    assert len(chunk([("Text", "x" * 4000)])) == 3


def test_old_versions_and_model_changes_excluded(knowledge):
    k = knowledge
    sid = upload(k).json()["id"]
    approve(k, sid)
    run_one(k.engine, k.store, FakeEmbeddings())
    with Session(k.engine) as db:
        d = db.scalar(select(KnowledgeDocument))
        did = str(d.id)
    assert (
        k.client.post(f"/api/v1/admin/knowledge/{did}/reindex", headers=k.admin).status_code == 200
    )
    with Session(k.engine) as db:
        assert not list(db.execute(eligible_query(FakeEmbeddings.model)))
    run_one(k.engine, k.store, FakeEmbeddings())
    with Session(k.engine) as db:
        d = db.scalar(select(KnowledgeDocument))
        assert d.version == 2
        assert len(list(db.execute(eligible_query(FakeEmbeddings.model)))) == 1
        assert len(list(db.scalars(select(KnowledgeChunk)))) == 2
        assert not list(db.execute(eligible_query("a-different-model")))


def test_removal_during_processing_cannot_reactivate(knowledge):
    k = knowledge
    sid = upload(k).json()["id"]
    approve(k, sid)
    with Session(k.engine) as db:
        did = str(db.scalar(select(KnowledgeDocument.id)))

    class Removing(FakeEmbeddings):
        def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
            response = k.client.delete(f"/api/v1/admin/knowledge/{did}", headers=k.admin)
            assert response.status_code == 200
            return super().embed(texts, task)

    assert run_one(k.engine, k.store, Removing())
    with Session(k.engine) as db:
        assert not list(db.execute(eligible_query(FakeEmbeddings.model)))
        assert db.scalar(select(ProcessingJob)).error_code == "removed_by_admin"


def test_vector_search_postgres(knowledge):
    from app.knowledge.retrieval import retrieve

    k = knowledge
    if k.engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL vector distance operator")
    sid = upload(k).json()["id"]
    approve(k, sid)
    run_one(k.engine, k.store, FakeEmbeddings())
    matches = retrieve(k.engine, FakeEmbeddings(), "What is force?", "Physics")
    assert len(matches) == 1
    assert "Force equals" in matches[0]["content"]
    assert retrieve(k.engine, FakeEmbeddings(), "What is force?", "Chemistry") == []


def test_sourced_answer_persists_references_and_rechecks_removal(knowledge):
    from uuid import uuid4

    from app.knowledge.retrieval import SourcedAnswer
    from app.models.knowledge import MessageSource

    k = knowledge
    sid = upload(k).json()["id"]
    approve(k, sid)
    run_one(k.engine, k.store, FakeEmbeddings())
    with Session(k.engine) as db:
        chunk = db.scalar(select(KnowledgeChunk))
        sources = [
            {
                "id": "S1",
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "title": "Mechanics",
                "location": "Text",
            }
        ]

    class SourcedProvider:
        available = True
        mode = "verification"

        async def generate(self, context):
            return SourcedAnswer("Force equals mass times acceleration [S1].", sources)

    k.client.app.state.academic_provider = SourcedProvider()
    cid = k.client.post(
        "/api/v1/conversations", headers=k.contributor, json={"client_id": str(uuid4())}
    ).json()["id"]
    r = k.client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=k.contributor,
        json={"request_id": str(uuid4()), "content": "What is force?"},
    )
    assert r.status_code == 201, r.text
    assert "Reference materials retrieved" in r.json()["messages"][-1]["content"]
    with Session(k.engine) as db:
        assert db.scalar(select(MessageSource)).title == "Mechanics"
    k.client.delete(f"/api/v1/admin/knowledge/{sources[0]['document_id']}", headers=k.admin)
    r = k.client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=k.contributor,
        json={"request_id": str(uuid4()), "content": "Explain the same source"},
    )
    assert r.status_code == 503
    assert r.json()["request"]["error_code"] == "unavailable"


def test_exhausted_crash_lease_becomes_recoverable(knowledge):
    from datetime import timedelta

    from app.auth.crypto import now

    k = knowledge
    sid = upload(k).json()["id"]
    approve(k, sid)
    with Session(k.engine) as db:
        job = db.scalar(select(ProcessingJob))
        job.state, job.attempts = "processing", 3
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    assert not run_one(k.engine, k.store, FakeEmbeddings())
    with Session(k.engine) as db:
        job = db.scalar(select(ProcessingJob))
        assert job.state == "failed" and job.error_code == "attempts_exhausted"
        assert db.scalar(select(KnowledgeDocument)).processing_status == "failed"
