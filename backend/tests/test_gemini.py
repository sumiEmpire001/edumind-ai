import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from google.genai import errors, types

from app.ai.gemini import GeminiProvider
from app.ai.provider import AcademicError, MediaPart, Turn


def provider(effects):
    p = object.__new__(GeminiProvider)
    p.key = "test-only-key"
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


def test_image_bytes_are_passed_as_inline_parts():
    p = provider([reply()])
    asyncio.run(
        p.generate([Turn("user", "Explain this image", (MediaPart("image/png", b"fixture"),))])
    )
    content = p.client.aio.models.generate_content.call_args.kwargs["contents"][0]
    assert content.parts[0].text == "Explain this image"
    assert content.parts[1].inline_data.data == b"fixture"
    assert content.parts[1].inline_data.mime_type == "image/png"


def test_flash_reasoning_is_bounded_without_relaxing_answer_limit():
    p = provider([reply()])
    p.model = "gemini-2.5-flash"
    asyncio.run(p.generate([Turn("user", "Draft a substantive report section.")]))
    config = p.client.aio.models.generate_content.call_args.kwargs["config"]
    assert config.thinking_config.thinking_budget == 128
    assert config.max_output_tokens == 16384


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
        (reply("x" * 60001), "provider_failure"),
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


def test_research_returns_only_provider_grounded_links():
    response = reply("Current answer")
    response.candidates[0].grounding_metadata = types.GroundingMetadata(
        grounding_chunks=[
            types.GroundingChunk(web=types.GroundingChunkWeb(title="Example", uri=url))
            for url in [
                "https://example.org/evidence",
                "https://example.org/evidence",
                "javascript:alert(1)",
                "https://someone@example.org/unsafe",
            ]
        ],
        search_entry_point=types.SearchEntryPoint(
            rendered_content='<a href="https://www.google.com/search?q=example">Look up</a>'
            '<a href="https://untrusted.example/search">Other link</a>'
        ),
    )
    p = provider([response])
    result = asyncio.run(p.research("What is current?"))
    assert result.answer == "Current answer"
    assert [source.url for source in result.sources] == ["https://example.org/evidence"]
    assert [link.title for link in result.suggestions] == ["Look up"]
    args = p.client.aio.models.generate_content.call_args.kwargs
    assert args["config"].tools[0].google_search is not None
    assert len(args["contents"]) == 1


def test_research_fails_closed_when_gemini_skips_grounding():
    response = reply("Unverified answer")
    response.candidates[0].grounding_metadata = None
    with pytest.raises(AcademicError, match="no_web_sources"):
        asyncio.run(provider([response]).research("What is current?"))


def test_long_answer_and_token_limited_draft_are_preserved():
    text = "Academic explanation. " * 1200
    p = provider([reply(text), reply(text, types.FinishReason.MAX_TOKENS)])
    assert asyncio.run(p.generate([Turn("user", "Write a detailed report")])) == text.strip()
    partial = asyncio.run(p.generate([Turn("user", "Write a detailed report")]))
    assert partial.startswith(text.strip())
    assert "Response length limit reached." in partial


def test_studio_section_keeps_its_bounded_generation_budget():
    p = provider([reply()])
    asyncio.run(p.generate([Turn("user", "Draft one section", output_tokens=4096)]))
    assert p.client.aio.models.generate_content.call_args.kwargs["config"].max_output_tokens == 4096
