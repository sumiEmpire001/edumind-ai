import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.session import build_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = build_engine(config)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(
        title="EduMind AI API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if config.app_env == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if config.app_env == "production" else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger("edumind").error(
                "unhandled_error", extra={"request_id": request.state.request_id}
            )
            response = JSONResponse(
                {"detail": "The service could not complete this request."}, status_code=500
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(router)
    return app
