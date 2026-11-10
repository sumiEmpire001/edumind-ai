import asyncio
from unittest.mock import patch

import httpx
import pytest

from app.ai.provider import AcademicError
from app.ai.public_search import search_public_sources


def search_with(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch("app.ai.public_search.httpx.AsyncClient", return_value=client):
        return asyncio.run(search_public_sources("incident response"))


def test_public_search_returns_attributed_plain_text_sources():
    def respond(request):
        if request.url.host == "en.wikipedia.org":
            assert request.url.params["q"] == "incident response"
            return httpx.Response(
                200,
                json={
                    "pages": [
                        {
                            "key": "Incident_response",
                            "title": "Incident response",
                            "excerpt": "<span>Incident</span> &amp; response",
                        }
                    ]
                },
            )
        assert request.url.params["query.bibliographic"] == "incident response"
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "DOI": "10.1000/response",
                            "title": ["An incident response study"],
                            "published": {"date-parts": [[2026]]},
                        }
                    ]
                }
            },
        )

    sources = search_with(respond).sources
    assert [item.publisher for item in sources] == ["Wikipedia", "Crossref"]
    assert sources[0].description == "Incident & response"
    assert sources[1].url == "https://doi.org/10.1000/response"
    assert sources[1].description == "2026"


def test_public_search_does_not_turn_provider_errors_into_empty_results():
    with pytest.raises(AcademicError, match="provider_failure"):
        search_with(lambda _: httpx.Response(503))
