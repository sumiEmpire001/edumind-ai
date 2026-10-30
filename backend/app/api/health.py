import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.database.session import check_database

router = APIRouter(prefix="/api/v1/health", tags=["health"])
logger = logging.getLogger("edumind")


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    try:
        available = check_database(request.app.state.engine)
    except Exception:
        available = False
    if not available:
        logger.warning("readiness_failed", extra={"request_id": request.state.request_id})
    return JSONResponse(
        {"status": "ready" if available else "unavailable"}, status_code=200 if available else 503
    )
