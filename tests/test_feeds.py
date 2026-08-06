from pathlib import Path

import requests

from feeds import FEEDS, fetch_all_feeds, parse_feed

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


def test_feeds_lists_all_14_blogs():
    assert len(FEEDS) == 14
    assert all(url.startswith("https://aws.amazon.com/blogs/") for url in FEEDS.values())
    assert all(url.endswith("/feed/") for url in FEEDS.values())


def test_parse_feed_extracts_articles():
    articles = parse_feed("Storage", FIXTURE.read_bytes())
    assert len(articles) == 2
    first = articles[0]
    assert first.blog == "Storage"
    assert first.title == "Announcing Amazon S3 Widgets"
    assert first.url == "https://aws.amazon.com/blogs/storage/s3-widgets/"
    assert first.guid == "https://aws.amazon.com/blogs/storage/?p=1001"
    assert "full body" in first.content
    assert first.published is not None and first.published.year == 2026


def test_parse_feed_falls_back_to_excerpt_when_no_content():
    articles = parse_feed("Storage", FIXTURE.read_bytes())
    second = articles[1]
    assert second.content == second.excerpt == "A short excerpt about EBS snapshots."


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


def test_fetch_all_feeds_skips_broken_feed(monkeypatch):
    def fake_get(url, **kwargs):
        if "broken" in url:
            raise requests.ConnectionError("boom")
        return FakeResponse(FIXTURE.read_bytes())

    monkeypatch.setattr("feeds.requests.get", fake_get)
    feeds = {
        "Storage": "https://aws.amazon.com/blogs/storage/feed/",
        "Broken": "https://aws.amazon.com/blogs/broken/feed/",
    }
    articles = fetch_all_feeds(feeds)
    assert len(articles) == 2
    assert {a.blog for a in articles} == {"Storage"}
