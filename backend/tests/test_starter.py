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
    assert install(k.engine, k.store) == 5
    assert install(k.engine, k.store) == 0
    with Session(k.engine) as db:
        assert db.scalar(select(func.count()).select_from(KnowledgeSubmission)) == 5
        count = db.scalar(select(func.count()).select_from(KnowledgeChunk))
        assert count > 30
        for c in db.scalars(select(KnowledgeChunk)):
            assert "creativecommons.org/licenses/" in c.content
        for d in db.scalars(select(KnowledgeDocument)):
            d.active = False
        db.commit()
    assert install(k.engine, k.store) == 0
    assert evidence(k.engine, "What is random sampling?") == []


def test_starter_retrieval_evaluation(knowledge):
    k = knowledge
    install(k.engine, k.store)
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
