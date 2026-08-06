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


def test_no_new_articles_sends_nothing(wired, monkeypatch):
    calls, _ = wired
    monkeypatch.setattr(handler, "filter_new", lambda a: [])
    result = handler.lambda_handler({}, None)
    assert calls == []
    assert result == {"new_articles": 0, "messages_sent": 0}


def test_failed_send_does_not_mark_seen(wired, monkeypatch):
    calls, _ = wired

    def boom(messages, token, chat_id):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(handler, "send_digest", boom)
    with pytest.raises(RuntimeError, match="telegram down"):
        handler.lambda_handler({}, None)
    assert "mark" not in calls
