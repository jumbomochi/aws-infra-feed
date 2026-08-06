from datetime import datetime, timezone

import pytest

import handler
from config import Config


@pytest.fixture
def wired(monkeypatch, make_article):
    """Wire every collaborator to fakes; record send/mark call order."""
    calls = []
    articles = [make_article(guid="g1"), make_article(guid="g2")]
    monkeypatch.setattr(handler, "load_config", lambda: Config("tok", "42", "gem"))
    monkeypatch.setattr(handler, "fetch_all_feeds", lambda: articles)
    monkeypatch.setattr(handler, "filter_new", lambda a: a)
    monkeypatch.setattr(handler, "make_client", lambda api_key: object())
    monkeypatch.setattr(handler, "summarize", lambda c, a: f"summary of {a.guid}")
    monkeypatch.setattr(
        handler, "send_digest", lambda m, token, chat_id: calls.append("send")
    )
    monkeypatch.setattr(handler, "mark_seen", lambda a: calls.append("mark"))
    return calls, articles


def test_happy_path_sends_then_marks(wired):
    calls, articles = wired
    result = handler.lambda_handler({}, None)
    assert calls == ["send", "mark"]
    assert result == {"new_articles": 2, "messages_sent": 1}
    assert articles[0].summary == "summary of g1"


def test_no_new_articles_sends_heartbeat(wired, monkeypatch):
    calls, _ = wired
    sent_messages = []
    monkeypatch.setattr(handler, "filter_new", lambda a: [])
    monkeypatch.setattr(
        handler,
        "send_digest",
        lambda m, token, chat_id: (sent_messages.extend(m), calls.append("send")),
    )
    result = handler.lambda_handler({}, None)
    assert calls == ["send"]  # heartbeat sent, nothing marked seen
    assert result == {"new_articles": 0, "messages_sent": 1}
    assert "No new articles today." in sent_messages[0]


def test_caps_run_to_newest_articles(wired, monkeypatch, make_article):
    _, _ = wired
    monkeypatch.setattr(handler, "MAX_ARTICLES_PER_RUN", 2)
    articles = [
        make_article(guid="oldest", published=datetime(2026, 8, 1, tzinfo=timezone.utc)),
        make_article(guid="newest", published=datetime(2026, 8, 3, tzinfo=timezone.utc)),
        make_article(guid="middle", published=datetime(2026, 8, 2, tzinfo=timezone.utc)),
        make_article(guid="undated"),
    ]
    monkeypatch.setattr(handler, "fetch_all_feeds", lambda: articles)
    marked = []
    monkeypatch.setattr(handler, "mark_seen", lambda a: marked.extend(a))
    result = handler.lambda_handler({}, None)
    assert result["new_articles"] == 2
    assert {a.guid for a in marked} == {"newest", "middle"}


def test_failed_send_does_not_mark_seen(wired, monkeypatch):
    calls, _ = wired

    def boom(messages, token, chat_id):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(handler, "send_digest", boom)
    with pytest.raises(RuntimeError, match="telegram down"):
        handler.lambda_handler({}, None)
    assert "mark" not in calls
