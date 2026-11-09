"""Optional text backup for the existing Gemini chat provider."""

import asyncio
import logging

import httpx

from app.ai.gemini import SYSTEM, GeminiProvider
from app.ai.gemini import build_provider as build_gemini_provider
from app.ai.provider import AcademicError, Turn
from app.core.config import Settings

logger = logging.getLogger("edumind")


class OpenAIBackup:
    def __init__(self, key: str, model: str):
        self.model = model
        self.client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1/",
            headers={"Authorization": f"Bearer {key}"},
            trust_env=False,
        )

    async def generate(self, context: list[Turn]) -> str:
        try:
            response = await self.client.post(
                "chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        *({"role": turn.role, "content": turn.content} for turn in context),
                    ],
                    "max_completion_tokens": 4096,
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise AcademicError("timeout") from None
        except httpx.HTTPStatusError as exc:
            code = "rate_limited" if exc.response.status_code == 429 else "provider_failure"
            raise AcademicError(code) from None
        except httpx.RequestError:
            raise AcademicError() from None

        try:
            choice = response.json()["choices"][0]
            if choice["finish_reason"] != "stop":
                raise AcademicError()
            answer = choice["message"]["content"]
        except (KeyError, IndexError, ValueError, TypeError):
            raise AcademicError() from None
        if not isinstance(answer, str) or not answer.strip():
            raise AcademicError("empty_response")
        if len(answer) > 12000:
            raise AcademicError()
        return answer.strip()

    async def aclose(self):
        await self.client.aclose()


class BackupRouter:
    available = True
    mode = "gemini"

    def __init__(self, primary: GeminiProvider, backup: OpenAIBackup, budget: float):
        self.primary = primary
        self.backup = backup
        self.budget = budget

    async def generate(self, context: list[Turn]) -> str:
        if any(turn.media for turn in context):
            return await self.primary.generate(context)

        async with asyncio.timeout(self.budget):
            try:
                async with asyncio.timeout(self.budget * 0.6):
                    return await self.primary.generate(context)
            except TimeoutError:
                reason = "timeout"
            except AcademicError as exc:
                if exc.code not in {"timeout", "rate_limited"}:
                    raise
                reason = exc.code

            logger.info("academic_backup_attempt reason=%s", reason)
            return await self.backup.generate(context)

    async def aclose(self):
        try:
            await self.primary.aclose()
        finally:
            await self.backup.aclose()


def build_provider(config: Settings):
    primary = build_gemini_provider(config)
    key = config.openai_backup_api_key
    if isinstance(primary, GeminiProvider) and key and key.get_secret_value().strip():
        return BackupRouter(
            primary,
            OpenAIBackup(key.get_secret_value().strip(), config.openai_backup_model),
            config.chat_timeout_seconds,
        )
    return primary
