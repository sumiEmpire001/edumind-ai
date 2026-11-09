from unittest.mock import AsyncMock

from app.ai.provider import AcademicError
from app.ai.research import ResearchResult, WebLink
from tests.test_auth import api as api
from tests.test_auth import auth, login, register
from tests.test_auth import engine as engine


def test_research_requires_authentication_and_origin(api):
    client, _, _ = api
    search = AsyncMock(
        return_value=ResearchResult(
            answer="A current fact.",
            sources=[WebLink(title="Evidence", url="https://example.org/evidence")],
            suggestions=[],
        )
    )
    client.app.state.research = search
    query = {"question": "What is current?"}
    assert client.post("/api/v1/research", json=query).status_code == 401
    register(client)
    headers = auth(login(client))
    assert (
        client.post(
            "/api/v1/research",
            json=query,
            headers={**headers, "Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    search.assert_not_called()
    result = client.post("/api/v1/research", json=query, headers=headers)
    assert result.status_code == 200
    assert result.json()["sources"][0]["url"] == "https://example.org/evidence"
    search.assert_awaited_once_with(query["question"])


def test_research_surfaces_missing_evidence(api):
    client, _, _ = api
    register(client)
    headers = auth(login(client))
    client.app.state.research = AsyncMock(side_effect=AcademicError("no_web_sources"))
    result = client.post(
        "/api/v1/research", json={"question": "Verify a recent change"}, headers=headers
    )
    assert result.status_code == 424
    assert "sources" in result.json()["detail"]
