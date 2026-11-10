"""Live discovery across public reference articles and scholarly metadata."""

import asyncio
import re
from html import unescape
from urllib.parse import quote

import httpx

from app.ai.provider import AcademicError
from app.ai.research import ResearchResult, WebLink

WIKIPEDIA = "https://en.wikipedia.org"
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "EduMindAI/1.0 (https://github.com/sumiEmpire001/edumind-ai)"


async def wikipedia(client: httpx.AsyncClient, question: str) -> list[WebLink]:
    reply = await client.get(
        f"{WIKIPEDIA}/w/rest.php/v1/search/page", params={"q": question, "limit": 5}
    )
    reply.raise_for_status()
    return [
        WebLink(
            title=page["title"][:220],
            url=f"{WIKIPEDIA}/wiki/{quote(page['key'], safe='')}",
            publisher="Wikipedia",
            description=unescape(re.sub(r"<[^>]*>", "", page.get("excerpt") or ""))[:380],
        )
        for page in reply.json()["pages"]
        if page.get("key") and page.get("title")
    ]


async def crossref(client: httpx.AsyncClient, question: str) -> list[WebLink]:
    reply = await client.get(
        CROSSREF,
        params={
            "query.bibliographic": question,
            "rows": 5,
            "select": "DOI,title,published,container-title",
        },
    )
    reply.raise_for_status()
    results = []
    for work in reply.json()["message"]["items"]:
        doi = work.get("DOI", "")
        titles = work.get("title") or []
        if not titles or not titles[0] or not re.fullmatch(r"10\.\d{4,}/\S+", doi):
            continue
        journal = (work.get("container-title") or [""])[0]
        dates = (work.get("published") or {}).get("date-parts") or [[]]
        year = str(dates[0][0]) if dates[0] else ""
        results.append(
            WebLink(
                title=unescape(re.sub(r"<[^>]*>", "", titles[0]))[:220],
                url=f"https://doi.org/{quote(doi, safe='/')}",
                publisher="Crossref",
                description=" · ".join(filter(None, [journal, year]))[:380],
            )
        )
    return results


async def search_public_sources(question: str) -> ResearchResult:
    async with httpx.AsyncClient(
        timeout=6, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    ) as client:
        batches = await asyncio.gather(
            wikipedia(client, question), crossref(client, question), return_exceptions=True
        )
    links = {}
    for batch in batches:
        if isinstance(batch, list):
            links.update((link.url, link) for link in batch)
        elif not isinstance(batch, (httpx.HTTPError, ValueError, TypeError, KeyError)):
            raise batch
    if all(isinstance(batch, BaseException) for batch in batches):
        raise AcademicError("provider_failure")
    if not links:
        raise AcademicError("no_web_sources")
    incomplete = any(isinstance(batch, BaseException) for batch in batches)
    return ResearchResult(
        answer=(
            "One source is temporarily unavailable. Showing results from the other source."
            if incomplete
            else "Open a result to check its date and read the original source."
        ),
        sources=list(links.values()),
        suggestions=[],
    )
