import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.ai.provider import AcademicError, MediaPart, Turn
from app.ai.routing import BackupRouter, OpenAIBackup

CONTEXT = [Turn("user", "What is 2 + 2?")]


@pytest.mark.parametrize("code", ["rate_limited", "timeout"])
def test_gemini_transient_error_uses_backup(code):
    primary = SimpleNamespace(generate=AsyncMock(side_effect=AcademicError(code)))
    backup = SimpleNamespace(generate=AsyncMock(return_value="4"))
    assert asyncio.run(BackupRouter(primary, backup, 1).generate(CONTEXT)) == "4"
    backup.generate.assert_awaited_once_with(CONTEXT)


def test_slow_primary_leaves_time_for_backup():
    backup = SimpleNamespace(generate=AsyncMock(return_value="4"))

    async def slow(_context):
        await asyncio.sleep(2)

    primary = SimpleNamespace(generate=slow)
    assert asyncio.run(BackupRouter(primary, backup, 0.1).generate(CONTEXT)) == "4"


@pytest.mark.parametrize(
    "context,error",
    [
        (CONTEXT, AcademicError("provider_failure")),
        (CONTEXT, asyncio.CancelledError()),
        ([Turn("user", "Image", (MediaPart("image/png", b"fixture"),))], AcademicError("timeout")),
    ],
)
def test_rejected_or_cancelled_requests_do_not_use_backup(context, error):
    primary = SimpleNamespace(generate=AsyncMock(side_effect=error))
    backup = SimpleNamespace(generate=AsyncMock())
    with pytest.raises(type(error)):
        asyncio.run(BackupRouter(primary, backup, 1).generate(context))
    backup.generate.assert_not_awaited()


def test_backup_request_preserves_tutor_instructions_and_message_roles():
    async def check():
        def reply(request):
            assert str(request.url) == "https://api.openai.com/v1/chat/completions"
            payload = json.loads(request.content)
            assert "academic tutor" in payload["messages"][0]["content"]
            assert payload["messages"][1] == {"role": "user", "content": CONTEXT[0].content}
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "stop", "message": {"content": " 4 "}}]}
            )

        backup = OpenAIBackup("test-only", "gpt-4.1-mini")
        await backup.aclose()
        async with httpx.AsyncClient(
            base_url="https://api.openai.com/v1/", transport=httpx.MockTransport(reply)
        ) as client:
            backup.client = client
            assert await backup.generate(CONTEXT) == "4"

    asyncio.run(check())
