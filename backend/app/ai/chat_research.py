"""Route study questions to free public research when current evidence is needed."""

import asyncio
import json
import re
from dataclasses import replace

from fastapi import HTTPException

from app.ai.provider import AcademicError, Turn
from app.ai.research import ResearchResult, safe_url

RESEARCH_INTENT = re.compile(
    r"\b(?:latest|up.to.date|as of today|today|tonight|yesterday|right now|this year|"
    r"this (?:week|month|semester)|recent (?:news|updates?|research|studies|papers)|"
    r"current (?:price|weather|news|rates?|president|governor|vice.chancellor|"
    r"deadline|status|version|exchange rate)|"
    r"(?:admission|application|registration) deadlines?|who is the (?:president|governor)|"
    r"search (?:the )?(?:web|internet|online)|look (?:it |this )?up|"
    r"^research |please research |verify (?:this|the) claim|"
    r"(?:find|cite|give|include|with|provide) "
    r"(?:me |the |some |reliable |academic |peer.reviewed )*"
    r"(?:sources|citations|references|papers|studies|evidence)|"
    r"(?:is|are|when (?:is|are|will)) .{0,70}(?:admissions?|applications?|registration)"
    r".{0,40}(?:open|clos(?:e|ing)|deadline))\b",
    re.IGNORECASE,
)


def should_research(question: str, mode: str, has_attachments: bool) -> bool:
    return (
        not has_attachments
        and mode != "off"
        and (mode == "on" or bool(RESEARCH_INTENT.search(question)))
    )


async def add_research(context: list[Turn], question: str, search) -> tuple[list[Turn], str, str]:
    try:
        async with asyncio.timeout(6):
            result: ResearchResult = await search(question)
    except (TimeoutError, AcademicError):
        result = ResearchResult(answer="", sources=[], suggestions=[])
    except HTTPException as exc:
        if exc.status_code != 429:
            raise
        result = ResearchResult(answer="", sources=[], suggestions=[])

    references, links = [], []
    for source in result.sources[:6]:
        url = safe_url(source.url)
        if not url or "<" in url or ">" in url:
            continue
        label = f"W{len(references) + 1}"
        references.append({"id": label, "title": source.title, "excerpt": source.description or ""})
        publisher = source.publisher if source.publisher in {"Wikipedia", "Crossref"} else "Source"
        title = " ".join(source.title.split())
        title = re.sub(r"([\\\[\]*_~`])", r"\\\1", title)
        links.append(f"- [{label} · {publisher} · {title}](<{url}>)")
    if not references:
        return context, "", "Web research found no usable sources for this question.\n\n"

    updated = [
        *context[:-1],
        replace(context[-1], web_context=json.dumps(references, ensure_ascii=False)),
    ]
    return updated, "\n\nWeb search results:\n" + "\n".join(links), ""
