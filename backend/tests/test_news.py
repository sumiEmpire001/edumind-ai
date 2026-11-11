import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import httpx

from app.ai.news import is_live_news, live_news, news_topic


def test_nigeria_today_only_returns_fresh_dated_headlines():
    now = datetime(2026, 11, 10, 17, tzinfo=UTC)
    rss = """
    <rss><channel>
      <item><title>Nigeria headline</title>
        <link>https://www.channelstv.com/current</link>
        <pubDate>Tue, 10 Nov 2026 15:15:00 +0000</pubDate>
      </item>
      <item><title>Yesterday headline</title>
        <link>https://www.channelstv.com/previous</link>
        <pubDate>Mon, 09 Nov 2026 19:00:00 +0000</pubDate>
      </item>
      <item><title>Unrelated world headline</title>
        <link>https://www.channelstv.com/world</link>
        <category>World News</category>
        <pubDate>Tue, 10 Nov 2026 16:00:00 +0000</pubDate>
      </item>
    </channel></rss>
    """

    def respond(request):
        if request.url.host == "www.channelstv.com":
            return httpx.Response(200, text=rss)
        return httpx.Response(503)

    question = "What is happening in Nigeria today?"
    assert is_live_news(question)
    assert not is_live_news("Explain Nigeria's constitutional history")
    assert not is_live_news("What happened in the French Revolution?")
    assert not is_live_news("What is fake news?")
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("app.ai.news.httpx.AsyncClient", return_value=client):
        result = asyncio.run(live_news(question, now))
    assert [source.title for source in result.sources] == ["Nigeria headline"]
    assert result.sources[0].description == "10 Nov 2026, 16:15 WAT"


def test_topic_search_supports_current_headlines_outside_nigeria():
    now = datetime(2026, 11, 10, 17, tzinfo=UTC)
    question = "What's happening in Ghana today?"
    assert is_live_news(question)
    assert news_topic(question) == "Ghana"

    def respond(request):
        assert request.url.host == "news.google.com"
        assert request.url.params["q"] == "Ghana when:2d"
        return httpx.Response(
            200,
            text="""
        <rss><channel><item>
            <title>Ghana headline</title><source>Fixture publisher</source>
            <link>https://news.google.com/rss/articles/example</link>
            <pubDate>Tue, 10 Nov 2026 15:15:00 GMT</pubDate>
        </item></channel></rss>""",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("app.ai.news.httpx.AsyncClient", return_value=client):
        result = asyncio.run(live_news(question, now))
    assert result.sources[0].publisher == "Fixture publisher"
    assert result.sources[0].description == "10 Nov 2026, 16:15 WAT"
