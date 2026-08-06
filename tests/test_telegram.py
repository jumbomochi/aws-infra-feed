from datetime import datetime

import pytest

import telegram
from telegram import SGT, format_digest, send_digest


def test_groups_by_blog_and_escapes_html(make_article):
    articles = [
        make_article(guid="1", blog="Storage", title="S3 <Widgets> & more", summary="Sum & sub."),
        make_article(guid="2", blog="Compute", title="Lambda news", summary="Faster."),
    ]
    messages = format_digest(articles, now=datetime(2026, 8, 6, 8, 0, tzinfo=SGT))
    assert len(messages) == 1
    text = messages[0]
    assert "AWS Blog Digest — Thu 06 Aug 2026" in text
    assert "S3 &lt;Widgets&gt; &amp; more" in text
    assert "Sum &amp; sub." in text
    assert '<a href="https://example.com/post">' in text
    assert text.index("<b>Compute</b>") < text.index("<b>Storage</b>")


def test_splits_long_digests(make_article):
    articles = [
        make_article(guid=str(i), title=f"Post {i}", summary="x" * 500)
        for i in range(20)
    ]
    messages = format_digest(articles)
    assert len(messages) > 1
    assert all(len(m) <= telegram.MAX_MESSAGE_CHARS for m in messages)


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_send_digest_posts_each_message(monkeypatch):
    sent = []

    def fake_post(url, json, timeout):
        sent.append((url, json))
        return FakeResponse({"ok": True})

    monkeypatch.setattr("telegram.requests.post", fake_post)
    send_digest(["one", "two"], token="TOKEN", chat_id="42")
    assert len(sent) == 2
    url, payload = sent[0]
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert payload["chat_id"] == "42"
    assert payload["text"] == "one"
    assert payload["parse_mode"] == "HTML"
    assert payload["disable_web_page_preview"] is True


def test_send_digest_raises_on_telegram_error(monkeypatch):
    monkeypatch.setattr(
        "telegram.requests.post",
        lambda *args, **kwargs: FakeResponse({"ok": False, "description": "bad"}),
    )
    with pytest.raises(RuntimeError, match="bad"):
        send_digest(["one"], token="T", chat_id="42")


def test_oversized_summary_is_truncated_under_limit(make_article):
    articles = [make_article(guid="1", summary="x" * 4500)]
    messages = format_digest(articles)
    assert all(len(m) <= telegram.MAX_MESSAGE_CHARS for m in messages)
    assert "…" in messages[0]


def test_blog_header_never_orphaned_from_first_article(make_article):
    articles = [
        make_article(guid=str(i), blog="AAA", title=f"Post {i}", summary="x" * 600)
        for i in range(6)
    ] + [make_article(guid="z", blog="ZZZ", title="Last post", summary="y" * 600)]
    messages = format_digest(articles)
    for message in messages:
        if "<b>ZZZ</b>" in message:
            assert "Last post" in message
