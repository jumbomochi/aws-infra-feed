import pytest

from models import Article


@pytest.fixture
def make_article():
    def _make(guid="guid-1", **overrides):
        defaults = dict(
            guid=guid,
            title="Some Title",
            url="https://example.com/post",
            blog="Storage",
            excerpt="An excerpt.",
            content="<p>Full body</p>",
        )
        defaults.update(overrides)
        return Article(**defaults)

    return _make


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
