import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.ai.gemini import build_provider
from app.ai.provider import AcademicProvider
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.health import router
from app.api.users import router as users_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.session import build_engine
from app.security.body_limit import BodyLimitMiddleware


def create_app(
    settings: Settings | None = None, provider: AcademicProvider | None = None
) -> FastAPI:
    config = settings or get_settings()
    if provider is not None and config.app_env != "test":
        raise ValueError("Phase 4 provider injection is restricted to isolated tests")
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = build_engine(config)
        try:
            yield
        finally:
            app.state.engine.dispose()
            close = getattr(app.state.academic_provider, "aclose", None)
            if close is not None:
                await close()

    app = FastAPI(
        title="EduMind AI API",
        version="0.4.0",
        lifespan=lifespan,
        docs_url=None if config.app_env == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if config.app_env == "production" else "/openapi.json",
    )
    app.state.settings = config
    app.state.academic_provider = provider or build_provider(config)
    app.add_middleware(BodyLimitMiddleware, limit=config.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        expose_headers=["X-Request-ID"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # FastAPI's default includes rejected input (possibly passwords); never echo it.
        return JSONResponse(
            {
                "detail": "Invalid request data.",
                "errors": [
                    {"field": error["loc"], "type": error["type"]} for error in exc.errors()
                ],
            },
            status_code=422,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request: Request, exc: SQLAlchemyError):
        logging.getLogger("edumind").error(
            f"database_unavailable kind={type(exc).__name__}",
            extra={"request_id": request.state.request_id},
        )
        return JSONResponse({"detail": "The service is temporarily unavailable."}, status_code=503)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception as exc:
            logging.getLogger("edumind").error(
                f"unhandled_error kind={type(exc).__name__}",
                extra={"request_id": request.state.request_id},
            )
            response = JSONResponse(
                {"detail": "The service could not complete this request."}, status_code=500
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        logging.getLogger("edumind").info(
            f"http_response method={request.method} status={response.status_code}",
            extra={"request_id": request.state.request_id},
        )
        return response

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(chat_router)
    return app
