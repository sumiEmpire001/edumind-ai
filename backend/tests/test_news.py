import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import httpx

from app.ai.news import is_nigeria_news, nigeria_news


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
    assert is_nigeria_news(question)
    assert not is_nigeria_news("Explain Nigeria's constitutional history")
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("app.ai.news.httpx.AsyncClient", return_value=client):
        result = asyncio.run(nigeria_news(question, now))
    assert [source.title for source in result.sources] == ["Nigeria headline"]
    assert result.sources[0].description == "10 Nov 2026, 16:15 WAT"
