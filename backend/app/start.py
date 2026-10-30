"""Single-instance test deployment entrypoint; production uses a release migration job."""

import asyncio
import logging
import os
import re

from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError

from alembic import command


def main():
    if os.environ.get("RUN_DATABASE_MIGRATIONS") == "true":
        try:
            command.upgrade(Config("alembic.ini"), "head")
        except SQLAlchemyError as exc:
            message = str(exc).lower()
            category = "database_error"
            for needle, label in [
                ("root certificate file", "missing_ca_certificate"),
                ("certificate verify failed", "certificate_verification_failed"),
                ("does not match host name", "certificate_hostname_mismatch"),
                ("does not support ssl", "database_ssl_unsupported"),
                ("password authentication failed", "database_credentials_invalid"),
                ("could not translate host", "database_hostname_invalid"),
                ("connection timed out", "database_connection_timeout"),
            ]:
                if needle in message:
                    category = label
                    break
            logging.error("migration_failed category=%s", category)
            raise SystemExit(1) from None
    if os.environ.get("CHECK_GEMINI_MODELS") == "true":
        from google import genai
        from google.genai import errors, types

        key = os.environ.get("GEMINI_API_KEY", "")
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=10000))
        try:
            models = [
                m.name
                for m in client.models.list()
                if m.supported_actions and "generateContent" in m.supported_actions
            ]
            logging.warning("gemini_available_models=%s", models[:35])
            response = client.models.generate_content(
                model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                contents="What is 2 + 2? Reply briefly.",
            )
            logging.warning("gemini_generation_check nonempty=%s", bool(response.text))
            from app.ai.gemini import GeminiProvider
            from app.ai.provider import AcademicError, Turn
            from app.core.config import get_settings

            async def probe():
                provider = GeminiProvider(get_settings())
                try:
                    answer = await provider.generate([Turn("user", "What is 2 + 2?")])
                    logging.warning("gemini_adapter_check nonempty=%s", bool(answer))
                except AcademicError as exc:
                    logging.warning("gemini_adapter_check category=%s", exc.code)
                finally:
                    await provider.aclose()

            asyncio.run(probe())
        except errors.APIError as exc:
            message = (exc.message or "").replace(key, "[REDACTED]") if key else "missing key"
            message = re.sub(r"AIza[\w-]+", "[REDACTED]", message)
            logging.warning("gemini_model_check status=%s detail=%s", exc.code, message[:400])
        finally:
            client.close()
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "8000"),
            "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
