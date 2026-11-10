"""Dated Nigeria headlines from fixed publisher feeds."""

import asyncio
import re
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree.ElementTree import ParseError

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from fastapi import HTTPException

from app.ai.provider import AcademicError
from app.ai.research import ResearchResult, WebLink, safe_url

WAT = timezone(timedelta(hours=1))
FEEDS = (
    ("Channels Television", "https://www.channelstv.com/feed/", "channelstv.com"),
    (
        "Premium Times",
        "https://www.premiumtimesng.com/category/news/top-news/feed",
        "premiumtimesng.com",
    ),
)
MAX_FEED = 512 * 1024
COUNTRY = re.compile(r"\b(?:nigeria|nigerian)\b", re.I)
NEWS_INTENT = re.compile(
    r"\b(?:news|headlines|current events|what(?: is|'s) happening|what happened)\b", re.I
)


def is_nigeria_news(question):
    return bool(COUNTRY.search(question) and NEWS_INTENT.search(question))


async def read_feed(client, feed, now, day):
    publisher, url, domain = feed
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        body = bytearray()
        async for part in response.aiter_bytes(chunk_size=8192):
            body.extend(part)
            if len(body) > MAX_FEED:
                return []
    items = []
    for item in ElementTree.fromstring(body).findall("./channel/item"):
        title = " ".join((item.findtext("title") or "").split())[:220]
        link = safe_url((item.findtext("link") or "").strip())
        if (
            not title
            or not link
            or not link.startswith((f"https://{domain}/", f"https://www.{domain}/"))
        ):
            continue
        categories = {entry.text.casefold() for entry in item.findall("category") if entry.text}
        if categories.intersection({"world news", "international"}):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None or not now - timedelta(hours=48) <= published <= now:
            continue
        local = published.astimezone(WAT)
        if day is not None and local.date() != day:
            continue
        items.append(
            (
                published,
                WebLink(
                    title=title,
                    url=link,
                    publisher=publisher,
                    description=local.strftime("%d %b %Y, %H:%M WAT"),
                ),
            )
        )
    return items


async def nigeria_news(question, now=None):
    now = now or datetime.now(UTC)
    local_day = now.astimezone(WAT).date()
    day = (
        local_day - timedelta(days=1)
        if re.search(r"\byesterday\b", question, re.I)
        else local_day
        if re.search(r"\btoday\b", question, re.I)
        else None
    )
    async with httpx.AsyncClient(
        timeout=5,
        follow_redirects=True,
        headers={"User-Agent": "EduMindAI/1.0 (https://github.com/sumiEmpire001/edumind-ai)"},
    ) as client:
        batches = await asyncio.gather(
            *(read_feed(client, feed, now, day) for feed in FEEDS), return_exceptions=True
        )
    items = []
    for batch in batches:
        if isinstance(batch, list):
            items.extend(batch)
        elif not isinstance(batch, (httpx.HTTPError, ParseError, DefusedXmlException)):
            raise batch
    links = {}
    seen = set()
    for _, article in sorted(items, key=lambda row: row[0], reverse=True):
        key = article.title.casefold()
        if article.url not in links and key not in seen:
            links[article.url] = article
            seen.add(key)
        if len(links) == 6:
            break
    answer = (
        f"Recent headlines from Nigerian newsrooms for {day.strftime('%d %B %Y')} (WAT)."
        if links and day
        else "Recent headlines from Nigerian newsrooms."
        if links
        else "I couldn’t verify headlines for that period from the connected news feeds."
    )
    return ResearchResult(answer=answer, sources=list(links.values()), suggestions=[])


async def news_reply(question, search, mode):
    if mode == "off":
        return "Turn on Web research to check recent Nigeria headlines."
    if not search:
        return "The live Nigeria news feeds are temporarily unavailable."
    try:
        async with asyncio.timeout(8):
            result = await search(question)
    except (TimeoutError, AcademicError):
        return "I couldn’t reach the Nigeria news feeds. Try again shortly."
    except HTTPException as exc:
        if exc.status_code != 429:
            raise
        return "Live news search is busy. Try again in a minute."
    lines = []
    for article in result.sources:
        url = safe_url(article.url)
        if not url or "<" in url or ">" in url:
            continue
        title = re.sub(r"([\\\[\]*_~])", r"\\\1", article.title)
        lines.append(f"- [{title}](<{url}>) — {article.publisher} · {article.description}")
    return "\n\n".join([result.answer, "\n".join(lines)]).strip()
