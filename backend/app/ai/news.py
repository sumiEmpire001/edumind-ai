"""Dated headlines from publisher feeds and topic-based news search."""

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
NEWS_SEARCH = ("Google News", "https://news.google.com/rss/search", "news.google.com")
MAX_FEED = 512 * 1024
NEWS_INTENT = re.compile(r"\b(?:headlines|current events|what(?: is|[’']s) happening)\b", re.I)


def is_live_news(question):
    if NEWS_INTENT.search(question):
        return True
    if re.match(r"^\s*(?:what (?:is|are)|define|explain)\b", question, re.I):
        return False
    return bool(
        re.search(r"\b(?:news|latest updates?|developments? today)\b", question, re.I)
        or (
            re.search(r"\bwhat happened\b", question, re.I)
            and re.search(r"\b(?:today|yesterday|this week|recently)\b", question, re.I)
        )
    )


def news_topic(question):
    topic = re.sub(
        r"^\s*(?:(?:what(?: is|[’']s) happening|what happened)|(?:give me|show me|find))\s*",
        "",
        question,
        flags=re.I,
    )
    topic = re.sub(
        r"\b(?:latest|breaking|current|news|headlines|updates?|today|yesterday|right now)\b",
        "",
        topic,
        flags=re.I,
    )
    topic = re.sub(r"^(?:(?:in|on|about|for|from|the)\s+)+", "", topic.strip(), flags=re.I)
    return " ".join(topic.strip(" ?.!").split())[:220] or "Nigeria"


async def read_feed(client, feed, now, day, *, topic=None):
    publisher, url, domain = feed
    params = (
        None
        if topic is None
        else {
            "q": f"{topic} when:2d",
            "hl": "en-NG",
            "gl": "NG",
            "ceid": "NG:en",
        }
    )
    async with client.stream("GET", url, params=params) as response:
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
        if topic is None and categories.intersection({"world news", "international"}):
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
        publisher_name = " ".join((item.findtext("source") or publisher).split())[:100]
        items.append(
            (
                published,
                WebLink(
                    title=title,
                    url=link,
                    publisher=publisher_name,
                    description=local.strftime("%d %b %Y, %H:%M WAT"),
                ),
            )
        )
    return items


async def live_news(question, now=None):
    topic = news_topic(question)
    local = topic.casefold() in {"nigeria", "nigerian"}
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
        requests = [read_feed(client, NEWS_SEARCH, now, day, topic=topic)]
        if local:
            requests.extend(read_feed(client, feed, now, day) for feed in FEEDS)
        batches = await asyncio.gather(*requests, return_exceptions=True)
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
        f"Recent headlines for {day.strftime('%d %B %Y')} (WAT)."
        if links and day
        else "Recent headlines from connected news sources."
        if links
        else "I couldn’t verify headlines for that period from the connected news feeds."
    )
    return ResearchResult(answer=answer, sources=list(links.values()), suggestions=[])


async def news_reply(question, search, mode):
    if mode == "off":
        return "Turn on Web research to check recent headlines."
    if not search:
        return "The live news feeds are temporarily unavailable."
    try:
        async with asyncio.timeout(8):
            result = await search(question)
    except (TimeoutError, AcademicError):
        return "I couldn’t reach the live news feeds. Try again shortly."
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
