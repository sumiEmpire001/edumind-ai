import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.ai.provider import AcademicError
from app.ai.research import ResearchResult
from app.auth.dependencies import DB, Current, trusted_origin
from app.schemas.identity import InputModel
from app.security.rate_limit import consume

router = APIRouter(prefix="/api/v1", tags=["research"])


class ResearchQuestion(InputModel):
    question: str = Field(min_length=5, max_length=2000)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value):
        return value.strip() if isinstance(value, str) else value


def limit_research(request: Request, user_id: str) -> None:
    consume(request, "web-research-user", user_id, 3, 60)
    consume(request, "web-research-project", "shared", 30, 86400)


@router.get("/research")
def research_availability(request: Request, current: Current) -> dict[str, bool]:
    return {"enabled": request.app.state.research is not None}


@router.post("/research", dependencies=[Depends(trusted_origin)], response_model=ResearchResult)
async def research(data: ResearchQuestion, request: Request, db: DB, current: Current):
    search = request.app.state.research
    if search is None:
        raise HTTPException(503, "Web research is unavailable.")
    user_id = str(current.user.id)
    db.rollback()
    await run_in_threadpool(limit_research, request, user_id)
    try:
        async with asyncio.timeout(35):
            return await search(data.question)
    except TimeoutError:
        raise HTTPException(504, "Web research timed out. Try a more focused question.") from None
    except AcademicError as exc:
        if exc.code == "no_web_sources":
            raise HTTPException(424, "No verifiable web sources were returned.") from None
        if exc.code == "rate_limited":
            raise HTTPException(
                429, "Web research is temporarily rate limited.", headers={"Retry-After": "60"}
            ) from None
        if exc.code == "timeout":
            raise HTTPException(504, "Web research timed out.") from None
        raise HTTPException(502, "Web research could not complete the search.") from None
