import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from google.genai import errors, types

from app.ai.gemini import GeminiProvider
from app.ai.provider import AcademicError, Turn


def provider(effects):
    p = object.__new__(GeminiProvider)
    p.model, p.attempts = "test-model", 3
    p.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(side_effect=effects)))
    )
    return p


def reply(text="Four", reason=types.FinishReason.STOP):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=reason)])


def test_followup():
    p = provider([reply()])
    assert (
        asyncio.run(p.generate([Turn("user", "2+2"), Turn("assistant", "4"), Turn("user", "Why?")]))
        == "Four"
    )
    args = p.client.aio.models.generate_content.call_args.kwargs
    assert [c.role for c in args["contents"]] == ["user", "model", "user"]
    assert "academic tutor" in args["config"].system_instruction


@pytest.mark.parametrize(
    "status,code,calls",
    [(429, "rate_limited", 3), (503, "provider_failure", 3), (401, "provider_failure", 1)],
)
def test_retry(status, code, calls):
    p = provider([errors.APIError(status, {"error": {"message": "SECRET"}})] * 3)
    with patch("app.ai.gemini.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(AcademicError) as caught:
            asyncio.run(p.generate([Turn("user", "question")]))
    assert str(caught.value) == code
    assert p.client.aio.models.generate_content.call_count == calls


@pytest.mark.parametrize(
    "response,code",
    [
        (reply(" "), "empty_response"),
        (reply(reason=types.FinishReason.SAFETY), "provider_failure"),
        (reply("x" * 12001), "provider_failure"),
    ],
)
def test_invalid(response, code):
    with pytest.raises(AcademicError, match=code):
        asyncio.run(provider([response]).generate([Turn("user", "question")]))


def test_timeout_recovery():
    p = provider([httpx.ReadTimeout("private"), reply()])
    with patch("app.ai.gemini.asyncio.sleep", new_callable=AsyncMock):
        assert asyncio.run(p.generate([Turn("user", "question")])) == "Four"


def test_cancel():
    p = provider([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(p.generate([Turn("user", "question")]))
    assert p.client.aio.models.generate_content.call_count == 1
