from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.knowledge.chat import evidence
from app.knowledge.starter import install, load_sources
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSubmission
from tests.test_auth import api as api
from tests.test_auth import engine as engine
from tests.test_knowledge import knowledge as knowledge


def test_starter_import_search_attribution_and_removed_documents(knowledge):
    k = knowledge
    assert install(k.engine, k.store) == len(load_sources())
    assert install(k.engine, k.store) == 0
    with Session(k.engine) as db:
        assert db.scalar(select(func.count()).select_from(KnowledgeSubmission)) == len(
            load_sources()
        )
        count = db.scalar(select(func.count()).select_from(KnowledgeChunk))
        assert count > 30
        for c in db.scalars(select(KnowledgeChunk)):
            assert "Source: https://" in c.content
        for d in db.scalars(select(KnowledgeDocument)):
            d.active = False
        db.commit()
    assert install(k.engine, k.store) == 0
    assert evidence(k.engine, "What is random sampling?") == []


def test_starter_retrieval_evaluation(knowledge):
    k = knowledge
    originals = [s for s in load_sources() if not s["id"].startswith("engineering-proposals-")]
    install(k.engine, k.store, originals)
    queries = [
        ("Explain random sampling", "Statistical study design"),
        ("What is anecdotal evidence?", "Statistical study design"),
        ("Explain quantitative data", "Research terminology"),
        ("Explain lab reports", "Laboratory reports"),
        ("What are feasibility reports?", "Long reports"),
        ("Explain project scope", "Defining a research project"),
    ]
    for question, expected in queries:
        matches = evidence(k.engine, question)
        assert any(expected in m["title"] for m in matches), (question, matches)
    assert evidence(k.engine, "What is zxqvnonexistent?") == []
    assert all(s["sections"] and s["url"].startswith("https://") for s in load_sources())


def test_project_topics_retrieval_and_removed_catalogue(knowledge):
    from app.knowledge.chat import find, topic

    k = knowledge
    source = next(s for s in load_sources() if s["discipline"] == "Electrical Engineering")
    install(k.engine, k.store, [source])
    query = topic(
        "Am in electrical engineering i need topic to submit "
        "to my Supervisor for my final year project"
    )
    answer, sources = find(k.engine, query)
    assert len(sources) == 5
    assert "solar charger" in answer.lower()
    assert "https://docs.arduino.cc" in answer
    with Session(k.engine) as db:
        for document in db.scalars(select(KnowledgeDocument)):
            document.active = False
        db.commit()
    assert find(k.engine, query)[1] == []


def test_student_gets_project_topics_without_provider(knowledge):
    from uuid import uuid4

    from app.ai.provider import UnconfiguredProvider
    from tests.test_auth import auth, login, register

    k = knowledge
    source = next(s for s in load_sources() if s["discipline"] == "Electrical Engineering")
    install(k.engine, k.store, [source])
    k.client.app.state.academic_provider = UnconfiguredProvider()
    register(k.client, email="catalogue-reader@example.com")
    headers = auth(login(k.client, email="catalogue-reader@example.com"))
    cid = str(uuid4())
    assert (
        k.client.post("/api/v1/conversations", headers=headers, json={"client_id": cid}).status_code
        == 201
    )
    r = k.client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers,
        json={
            "request_id": str(uuid4()),
            "content": "Suggest electrical engineering final year project topics",
        },
    )
    assert r.status_code == 201, r.text
    assert "solar charger" in r.text.lower()
    assert r.json()["messages"][-1]["provider"] == "knowledge"
