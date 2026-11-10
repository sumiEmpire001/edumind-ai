import hashlib
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge import learning
from app.knowledge.worker import run_one
from app.models.identity import User
from app.models.learning import LearningQuery
from tests.test_auth import api as api
from tests.test_auth import auth, login, register
from tests.test_auth import engine as engine
from tests.test_knowledge import FakeEmbeddings, approve, upload
from tests.test_knowledge import knowledge as knowledge


def actors(api):
    client, engine, _ = api
    register(client)
    student = auth(login(client))
    aid = UUID(register(client, email="admin@example.com").json()["id"])
    with Session(engine) as db:
        db.get(User, aid).role = "admin"
        db.commit()
    return client, engine, student, auth(login(client, email="admin@example.com"))


def propose(client, student, question="What is acceleration?"):
    return client.post(
        "/api/v1/learning/examples",
        headers=student,
        json={"question": question, "consent_to_share": True},
    )


def review(client, admin, eid, **extra):
    return client.post(
        f"/api/v1/admin/learning/examples/{eid}/review",
        headers=admin,
        json={
            "status": "approved",
            "answer": "Acceleration is change in velocity per unit time.",
            "evidence": "Verified physics course notes, section 2",
            "rights_confirmed": True,
            **extra,
        },
    )


def test_consent_access_review_and_metrics(api):
    client, engine, student, admin = actors(api)
    assert (
        client.post(
            "/api/v1/learning/examples", headers=student, json={"question": "What is acceleration?"}
        ).status_code
        == 422
    )
    r = propose(client, student)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert propose(client, student, "  WHAT is acceleration? ").status_code == 409
    assert client.get("/api/v1/admin/learning/overview", headers=student).status_code == 403
    assert review(client, student, eid).status_code == 403
    assert review(client, admin, eid, rights_confirmed=False).status_code == 422
    assert (
        client.post(
            "/api/v1/learning/query", headers=student, json={"question": "acceleration"}
        ).json()["sources"]
        == []
    )
    assert review(client, admin, eid).status_code == 200
    found = client.post(
        "/api/v1/learning/query", headers=student, json={"question": "acceleration"}
    ).json()
    assert found["uses_gemini"] is False
    assert found["sources"][0]["kind"] == "reviewed_answer"
    with Session(engine) as db:
        assert db.scalar(select(LearningQuery)).source_count == 0
        assert "question" not in LearningQuery.__table__.columns
    stats = client.get("/api/v1/admin/learning/overview", headers=admin).json()
    assert stats["training_examples"] == 1
    assert stats["queries"] == 2 and stats["queries_with_sources"] == 1
    assert stats["gemini_replacement_ready"] is False
    assert review(client, admin, eid, status="rejected").status_code == 200
    assert (
        client.post(
            "/api/v1/learning/query", headers=student, json={"question": "acceleration"}
        ).json()["sources"]
        == []
    )


def test_export_holdout_and_ownership(api):
    client, _, student, admin = actors(api)
    train = propose(client, student).json()["id"]
    heldout = propose(client, student, "How do electric circuits work?").json()["id"]
    assert review(client, admin, train).status_code == 200
    assert (
        review(
            client,
            admin,
            heldout,
            split="evaluation",
            answer="Electric circuits allow current to flow around a complete path.",
        ).status_code
        == 200
    )
    assert review(client, admin, heldout, split="train").status_code == 409
    assert review(client, admin, heldout, status="rejected", split="evaluation").status_code == 200
    assert review(client, admin, heldout, split="train").status_code == 409
    assert review(client, admin, heldout, split="evaluation").status_code == 200
    assert (
        client.post(
            "/api/v1/learning/query", headers=student, json={"question": "circuits"}
        ).json()["sources"]
        == []
    )
    data = client.get("/api/v1/admin/learning/dataset", headers=admin).json()
    assert data["count"] == 1 and "circuits" not in data["jsonl"]
    assert hashlib.sha256(data["jsonl"].encode()).hexdigest() == data["sha256"]
    assert "owner_id" not in data["jsonl"]
    assert client.get("/api/v1/admin/learning/dataset", headers=student).status_code == 403
    assert client.get("/api/v1/learning/examples").status_code == 401
    register(client, email="other@example.com")
    other = auth(login(client, email="other@example.com"))
    assert client.get("/api/v1/learning/examples", headers=other).json() == []


def test_only_current_approved_document_versions(knowledge):
    k = knowledge
    sid = upload(k).json()["id"]
    assert (
        k.client.post(
            "/api/v1/learning/query", headers=k.contributor, json={"question": "acceleration"}
        ).json()["sources"]
        == []
    )
    assert approve(k, sid).status_code == 200
    assert run_one(k.engine, k.store, FakeEmbeddings())
    result = k.client.post(
        "/api/v1/learning/query", headers=k.contributor, json={"question": "acceleration"}
    )
    assert result.status_code == 200, result.text
    source = result.json()["sources"][0]
    assert source["kind"] == "document" and source["title"] == "Mechanics"
    assert (
        k.client.get("/api/v1/admin/learning/overview", headers=k.admin).json()["searchable_chunks"]
        == 1
    )
    assert (
        k.client.delete(
            f"/api/v1/admin/knowledge/{source['document_id']}", headers=k.admin
        ).status_code
        == 200
    )
    assert (
        k.client.post(
            "/api/v1/learning/query", headers=k.contributor, json={"question": "acceleration"}
        ).json()["sources"]
        == []
    )


def test_input_limits_origin_and_no_automatic_collection(api):
    client, _, student, admin = actors(api)
    assert (
        client.post(
            "/api/v1/learning/query", headers=student, json={"question": " " * 10}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/learning/query", headers=student, json={"question": "x" * 2001}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/learning/query",
            headers={**student, "Origin": "https://evil.test"},
            json={"question": "acceleration"},
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/admin/learning/overview", headers=admin).json()["training_examples"]
        == 0
    )


def test_readiness_revision_tracks_migration_head():
    from alembic.script import ScriptDirectory

    from app.database.session import SCHEMA_REVISION

    assert SCHEMA_REVISION == ScriptDirectory("alembic").get_current_head()


@pytest.mark.integration
def test_search_requests_more_specific_terms_before_ranking_broad_matches(api, monkeypatch):
    client, engine, student, admin = actors(api)
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL full-text search required")
    monkeypatch.setattr(learning, "MAX_RANKED_MATCHES", 1)
    for question in ("How do we calculate acceleration?", "When is acceleration constant?"):
        eid = propose(client, student, question).json()["id"]
        assert review(client, admin, eid).status_code == 200
    broad = client.post(
        "/api/v1/learning/query", headers=student, json={"question": "acceleration"}
    )
    assert broad.status_code == 200
    assert broad.json()["status"] == "refine_query"
    assert broad.json()["sources"] == []
    narrow = client.post(
        "/api/v1/learning/query", headers=student, json={"question": "constant acceleration"}
    ).json()
    assert narrow["status"] == "sources_found"
    assert len(narrow["sources"]) == 1


def test_admin_research_draft_stays_out_of_search_until_approved(api):
    client, _, student, admin = actors(api)
    draft = {
        "question": "What does LAUTECH publish about admissions?",
        "answer": "Synthetic fixture summary for a university admissions page.",
        "evidence": "https://example.org/university/admissions",
    }
    assert (
        client.post("/api/v1/admin/learning/drafts", headers=student, json=draft).status_code == 403
    )
    saved = client.post("/api/v1/admin/learning/drafts", headers=admin, json=draft)
    assert saved.status_code == 201
    assert saved.json()["status"] == "pending"
    assert saved.json()["evidence"] == draft["evidence"]
    query = {"question": "LAUTECH admissions"}
    assert not client.post("/api/v1/learning/query", headers=student, json=query).json()["sources"]
    assert (
        review(
            client, admin, saved.json()["id"], answer=draft["answer"], evidence=draft["evidence"]
        ).status_code
        == 200
    )
    result = client.post("/api/v1/learning/query", headers=student, json=query).json()
    assert result["sources"][0]["location"] == draft["evidence"]
