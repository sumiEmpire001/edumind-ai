"""Convert provider grounding metadata into safe, structured browser results."""

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from google.genai import types
from pydantic import BaseModel

from app.ai.provider import AcademicError


class WebLink(BaseModel):
    title: str
    url: str


class ResearchResult(BaseModel):
    answer: str
    sources: list[WebLink]
    suggestions: list[WebLink]


def safe_url(value: str | None) -> str | None:
    if not value or len(value) > 4000 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme == "https" and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return None


class SearchSuggestions(HTMLParser):
    """Extract links from the search widget without exposing provider HTML to the browser."""

    def __init__(self):
        super().__init__()
        self.links: list[WebLink] = []
        self.href: str | None = None
        self.label: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = safe_url(dict(attrs).get("href"))
            self.label.clear()

    def handle_data(self, data):
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self.href:
            return
        url = urlsplit(self.href)
        title = " ".join("".join(self.label).split())[:180]
        if url.hostname in {"www.google.com", "google.com"} and url.path == "/search" and title:
            self.links.append(WebLink(title=title, url=self.href))
        self.href = None


def grounded_result(response: types.GenerateContentResponse) -> ResearchResult:
    metadata = response.candidates[0].grounding_metadata
    if not metadata:
        raise AcademicError("no_web_sources")

    sources: dict[str, WebLink] = {}
    for chunk in metadata.grounding_chunks or []:
        web = chunk.web
        url = safe_url(web.uri) if web else None
        if url and url not in sources:
            title = (web.title or "").strip()[:220] or urlsplit(url).hostname
            sources[url] = WebLink(title=title, url=url)
        if len(sources) == 10:
            break
    if not sources:
        raise AcademicError("no_web_sources")

    parser = SearchSuggestions()
    if metadata.search_entry_point and metadata.search_entry_point.rendered_content:
        parser.feed(metadata.search_entry_point.rendered_content[:40_000])
        parser.close()
    return ResearchResult(
        answer=response.text.strip(), sources=list(sources.values()), suggestions=parser.links[:6]
    )
