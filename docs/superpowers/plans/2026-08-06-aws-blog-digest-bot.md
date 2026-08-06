# AWS Blog Digest Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily Telegram digest of new articles from 14 AWS blogs, summarized by Gemini, delivered by 8:00 AM SGT.

**Architecture:** A single Python Lambda triggered by an EventBridge cron at 23:50 UTC (7:50 AM SGT). Pipeline: fetch 14 RSS feeds → diff against a DynamoDB seen-articles table → summarize new articles with Gemini → send an HTML-formatted Telegram digest → mark articles seen (only after a successful send). Deployed with AWS SAM.

**Tech Stack:** Python 3.13, feedparser, requests, google-genai SDK, boto3/DynamoDB, Telegram Bot API, AWS SAM, pytest + moto.

**Spec:** `docs/superpowers/specs/2026-08-06-aws-blog-digest-bot-design.md`

## Global Constraints

- Gemini model is exactly `gemini-3.6-flash`, defined once as `GEMINI_MODEL` in `src/summarize.py`.
- Schedule is exactly `cron(50 23 * * ? *)` (7:50 AM SGT; Singapore has no DST).
- All 14 feeds from the spec must appear in `src/feeds.py`.
- Articles are marked seen in DynamoDB **only after** the Telegram send succeeds. Never before.
- A single failing feed or a failing Gemini call must never fail the run; a failing Telegram send must fail the run.
- Secrets (Telegram bot token, chat ID, Gemini API key) come from env vars first, then SSM Parameter Store under `/infra-feed/`. Never hardcoded, never in the SAM template.
- Lambda modules live flat in `src/` and import each other top-level (`from feeds import ...`), because SAM packages `src/` as the Lambda root. Tests reach them via `pythonpath = ["src"]` in `pyproject.toml`.
- Run tests from the repo root with `pytest` (or a single test with `pytest tests/test_feeds.py::test_name -v`).

---

### Task 1: Project scaffolding and Article model

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/requirements.txt`
- Create: `requirements-dev.txt`
- Create: `src/models.py`
- Create: `tests/conftest.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `Article` dataclass in `src/models.py` with fields `guid: str, title: str, url: str, blog: str, excerpt: str, content: str, published: datetime | None = None, summary: str = ""`. Also the `make_article` pytest fixture (a factory: `make_article(guid="guid-1", **overrides) -> Article`) used by every later test task.

- [ ] **Step 1: Write config files**

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`.gitignore`:

```
__pycache__/
*.pyc
.pytest_cache/
.aws-sam/
.venv/
```

`src/requirements.txt` (what SAM bundles into the Lambda — boto3 is provided by the runtime, so it is deliberately absent):

```
feedparser
requests
google-genai
```

`requirements-dev.txt`:

```
-r src/requirements.txt
boto3
moto[dynamodb,ssm]
pytest
```

- [ ] **Step 2: Install dev dependencies**

Run: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`

Use `.venv/bin/pytest` (or activate the venv) for every test run in this plan.

- [ ] **Step 3: Write the failing test**

`tests/test_models.py`:

```python
from models import Article


def test_article_defaults():
    article = Article(
        guid="g1",
        title="T",
        url="https://example.com",
        blog="Storage",
        excerpt="e",
        content="c",
    )
    assert article.published is None
    assert article.summary == ""
```

`tests/conftest.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 5: Write minimal implementation**

`src/models.py`:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    guid: str
    title: str
    url: str
    blog: str
    excerpt: str
    content: str
    published: datetime | None = None
    summary: str = ""
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src/requirements.txt requirements-dev.txt src/models.py tests/
git commit -m "feat: project scaffolding and Article model"
```

---

### Task 2: Feed fetching and parsing

**Files:**
- Create: `src/feeds.py`
- Create: `tests/fixtures/sample_feed.xml`
- Test: `tests/test_feeds.py`

**Interfaces:**
- Consumes: `Article` from `models` (Task 1)
- Produces: `FEEDS: dict[str, str]` (blog label → feed URL, all 14), `parse_feed(blog: str, xml: bytes) -> list[Article]`, `fetch_all_feeds(feeds: dict[str, str] = FEEDS) -> list[Article]`

- [ ] **Step 1: Write the fixture**

`tests/fixtures/sample_feed.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>AWS Storage Blog</title>
    <link>https://aws.amazon.com/blogs/storage/</link>
    <item>
      <title>Announcing Amazon S3 Widgets</title>
      <link>https://aws.amazon.com/blogs/storage/s3-widgets/</link>
      <guid isPermaLink="false">https://aws.amazon.com/blogs/storage/?p=1001</guid>
      <pubDate>Wed, 05 Aug 2026 16:00:00 +0000</pubDate>
      <description>A short excerpt about S3 widgets.</description>
      <content:encoded><![CDATA[<p>This is the full body of the S3 widgets announcement, with <b>rich</b> HTML.</p>]]></content:encoded>
    </item>
    <item>
      <title>EBS snapshots deep dive</title>
      <link>https://aws.amazon.com/blogs/storage/ebs-snapshots/</link>
      <guid isPermaLink="false">https://aws.amazon.com/blogs/storage/?p=1002</guid>
      <pubDate>Wed, 05 Aug 2026 12:00:00 +0000</pubDate>
      <description>A short excerpt about EBS snapshots.</description>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Write the failing tests**

`tests/test_feeds.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_feeds.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'feeds'`

- [ ] **Step 4: Write minimal implementation**

`src/feeds.py`:

```python
import calendar
import logging
from datetime import datetime, timezone

import feedparser
import requests

from models import Article

logger = logging.getLogger(__name__)

FEEDS = {
    "AWS News": "https://aws.amazon.com/blogs/aws/feed/",
    "Architecture": "https://aws.amazon.com/blogs/architecture/feed/",
    "Big Data": "https://aws.amazon.com/blogs/big-data/feed/",
    "Compute": "https://aws.amazon.com/blogs/compute/feed/",
    "Containers": "https://aws.amazon.com/blogs/containers/feed/",
    "Database": "https://aws.amazon.com/blogs/database/feed/",
    "Developer Tools": "https://aws.amazon.com/blogs/developer/feed/",
    "DevOps": "https://aws.amazon.com/blogs/devops/feed/",
    "Machine Learning": "https://aws.amazon.com/blogs/machine-learning/feed/",
    "Management & Governance": "https://aws.amazon.com/blogs/mt/feed/",
    "Public Sector": "https://aws.amazon.com/blogs/publicsector/feed/",
    "Quantum Computing": "https://aws.amazon.com/blogs/quantum-computing/feed/",
    "Security": "https://aws.amazon.com/blogs/security/feed/",
    "Storage": "https://aws.amazon.com/blogs/storage/feed/",
}

FETCH_TIMEOUT_SECONDS = 15
USER_AGENT = "aws-infra-feed/1.0 (personal digest bot)"


def parse_feed(blog: str, xml: bytes) -> list[Article]:
    parsed = feedparser.parse(xml)
    articles = []
    for entry in parsed.entries:
        guid = entry.get("id") or entry.get("link")
        if not guid:
            continue
        excerpt = entry.get("summary", "")
        content = entry.content[0].value if entry.get("content") else excerpt
        published = None
        if entry.get("published_parsed"):
            published = datetime.fromtimestamp(
                calendar.timegm(entry.published_parsed), tz=timezone.utc
            )
        articles.append(
            Article(
                guid=guid,
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                blog=blog,
                excerpt=excerpt,
                content=content,
                published=published,
            )
        )
    return articles


def fetch_all_feeds(feeds: dict[str, str] = FEEDS) -> list[Article]:
    articles = []
    for blog, url in feeds.items():
        try:
            response = requests.get(
                url,
                timeout=FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            articles.extend(parse_feed(blog, response.content))
        except Exception:
            logger.warning("Skipping feed %s (%s)", blog, url, exc_info=True)
    return articles
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_feeds.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/feeds.py tests/fixtures/sample_feed.xml tests/test_feeds.py
git commit -m "feat: fetch and parse the 14 AWS blog RSS feeds"
```

---

### Task 3: Seen-article state in DynamoDB

**Files:**
- Create: `src/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `Article` from `models`; `make_article` and `aws_env` fixtures (Task 1); env var `TABLE_NAME`
- Produces: `filter_new(articles: list[Article]) -> list[Article]`, `mark_seen(articles: list[Article]) -> None`, `SEEN_TTL_SECONDS`

- [ ] **Step 1: Write the failing tests**

`tests/test_state.py`:

```python
import boto3
import pytest
from moto import mock_aws

from state import SEEN_TTL_SECONDS, filter_new, mark_seen

TABLE = "seen-articles-test"


@pytest.fixture
def seen_table(aws_env, monkeypatch):
    monkeypatch.setenv("TABLE_NAME", TABLE)
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            AttributeDefinitions=[{"AttributeName": "guid", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "guid", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield boto3.resource("dynamodb").Table(TABLE)


def test_all_articles_new_on_empty_table(seen_table, make_article):
    articles = [make_article(guid="g1"), make_article(guid="g2")]
    assert filter_new(articles) == articles


def test_seen_articles_are_filtered_out(seen_table, make_article):
    articles = [make_article(guid="g1"), make_article(guid="g2")]
    mark_seen(articles[:1])
    assert filter_new(articles) == [articles[1]]


def test_mark_seen_sets_ttl(seen_table, make_article):
    mark_seen([make_article(guid="g1")])
    item = seen_table.get_item(Key={"guid": "g1"})["Item"]
    assert int(item["expires_at"]) > SEEN_TTL_SECONDS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'state'`

- [ ] **Step 3: Write minimal implementation**

`src/state.py`:

```python
import os
import time

import boto3

from models import Article

SEEN_TTL_SECONDS = 90 * 24 * 60 * 60


def _table():
    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def filter_new(articles: list[Article]) -> list[Article]:
    table = _table()
    new = []
    for article in articles:
        response = table.get_item(Key={"guid": article.guid})
        if "Item" not in response:
            new.append(article)
    return new


def mark_seen(articles: list[Article]) -> None:
    table = _table()
    expires_at = int(time.time()) + SEEN_TTL_SECONDS
    with table.batch_writer() as batch:
        for article in articles:
            batch.put_item(
                Item={
                    "guid": article.guid,
                    "title": article.title,
                    "expires_at": expires_at,
                }
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/state.py tests/test_state.py
git commit -m "feat: track seen articles in DynamoDB with 90-day TTL"
```

---

### Task 4: Config and secrets loading

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `aws_env` fixture (Task 1)
- Produces: `Config` dataclass with fields `telegram_bot_token: str, telegram_chat_id: str, gemini_api_key: str`; `load_config() -> Config` (env vars `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `GEMINI_API_KEY` win; otherwise SSM SecureStrings `/infra-feed/telegram-bot-token`, `/infra-feed/telegram-chat-id`, `/infra-feed/gemini-api-key`)

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
import boto3
import pytest
from moto import mock_aws

from config import Config, load_config

ENV_NAMES = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GEMINI_API_KEY"]


def test_env_vars_take_precedence(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    assert load_config() == Config("tok", "123", "gem")


def test_falls_back_to_ssm(aws_env, monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    with mock_aws():
        ssm = boto3.client("ssm")
        for name, value in [
            ("/infra-feed/telegram-bot-token", "tok"),
            ("/infra-feed/telegram-chat-id", "123"),
            ("/infra-feed/gemini-api-key", "gem"),
        ]:
            ssm.put_parameter(Name=name, Value=value, Type="SecureString")
        assert load_config() == Config("tok", "123", "gem")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Write minimal implementation**

`src/config.py`:

```python
import os
from dataclasses import dataclass

import boto3

PARAM_PREFIX = "/infra-feed"


@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    gemini_api_key: str


def load_config() -> Config:
    return Config(
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN", "telegram-bot-token"),
        telegram_chat_id=_get("TELEGRAM_CHAT_ID", "telegram-chat-id"),
        gemini_api_key=_get("GEMINI_API_KEY", "gemini-api-key"),
    )


def _get(env_name: str, param_name: str) -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    ssm = boto3.client("ssm")
    response = ssm.get_parameter(
        Name=f"{PARAM_PREFIX}/{param_name}", WithDecryption=True
    )
    return response["Parameter"]["Value"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: load secrets from env vars with SSM fallback"
```

---

### Task 5: Gemini summarizer with excerpt fallback

**Files:**
- Create: `src/summarize.py`
- Test: `tests/test_summarize.py`

**Interfaces:**
- Consumes: `Article` from `models`; `make_article` fixture (Task 1)
- Produces: `GEMINI_MODEL = "gemini-3.6-flash"`, `make_client(api_key: str) -> genai.Client`, `summarize(client, article: Article) -> str` (accepts `client=None` → returns stripped excerpt; any Gemini error → returns stripped excerpt)

- [ ] **Step 1: Write the failing tests**

`tests/test_summarize.py`:

```python
from types import SimpleNamespace

from summarize import GEMINI_MODEL, summarize


class FakeModels:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append({"model": model, "contents": contents})
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


class FakeClient:
    def __init__(self, text=None, error=None):
        self.models = FakeModels(text=text, error=error)


def test_uses_gemini_summary(make_article):
    client = FakeClient(text="  A tidy summary. ")
    article = make_article(content="<p>Long <b>body</b> here</p>")
    assert summarize(client, article) == "A tidy summary."
    call = client.models.calls[0]
    assert call["model"] == GEMINI_MODEL
    assert "Long body here" in call["contents"]
    assert "<b>" not in call["contents"]


def test_falls_back_to_excerpt_on_gemini_error(make_article):
    client = FakeClient(error=RuntimeError("quota"))
    article = make_article(excerpt="Short &amp; sweet <em>excerpt</em>.")
    assert summarize(client, article) == "Short & sweet excerpt."


def test_falls_back_to_excerpt_on_empty_response(make_article):
    client = FakeClient(text="")
    article = make_article(excerpt="Plain excerpt.")
    assert summarize(client, article) == "Plain excerpt."


def test_none_client_uses_excerpt(make_article):
    article = make_article(excerpt="Plain excerpt.")
    assert summarize(None, article) == "Plain excerpt."


def test_model_is_pinned():
    assert GEMINI_MODEL == "gemini-3.6-flash"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summarize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'summarize'`

- [ ] **Step 3: Write minimal implementation**

`src/summarize.py`:

```python
import html
import logging
import re

from google import genai

from models import Article

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.6-flash"
MAX_CONTENT_CHARS = 30_000

PROMPT = (
    "Summarize this AWS blog post in 2-3 plain sentences for a daily digest. "
    "Focus on what changed or what the reader can now do. "
    "No preamble, no markdown, no bullet points.\n\n"
    "Title: {title}\n\n{content}"
)


def make_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def summarize(client, article: Article) -> str:
    if client is None:
        return _strip_html(article.excerpt)
    try:
        content = _strip_html(article.content)[:MAX_CONTENT_CHARS]
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=PROMPT.format(title=article.title, content=content),
        )
        summary = (response.text or "").strip()
        if summary:
            return summary
        logger.warning("Empty Gemini response for %s", article.url)
    except Exception:
        logger.warning(
            "Gemini failed for %s; falling back to excerpt", article.url, exc_info=True
        )
    return _strip_html(article.excerpt)


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_summarize.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/summarize.py tests/test_summarize.py
git commit -m "feat: Gemini article summaries with RSS-excerpt fallback"
```

---

### Task 6: Telegram digest formatting and sending

**Files:**
- Create: `src/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Consumes: `Article` from `models`; `make_article` fixture (Task 1)
- Produces: `SGT` timezone constant, `MAX_MESSAGE_CHARS = 4000`, `format_digest(articles: list[Article], now: datetime | None = None) -> list[str]` (HTML-mode messages, grouped by blog, split under the limit), `send_digest(messages: list[str], token: str, chat_id: str) -> None` (raises on any failure)

- [ ] **Step 1: Write the failing tests**

`tests/test_telegram.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_telegram.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telegram'`

- [ ] **Step 3: Write minimal implementation**

`src/telegram.py`:

```python
import html
from datetime import datetime, timedelta, timezone

import requests

from models import Article

SGT = timezone(timedelta(hours=8))
MAX_MESSAGE_CHARS = 4000  # headroom under Telegram's 4096 hard limit
SEND_TIMEOUT_SECONDS = 15


def format_digest(articles: list[Article], now: datetime | None = None) -> list[str]:
    now = now or datetime.now(SGT)
    blocks = [f"<b>AWS Blog Digest — {now:%a %d %b %Y}</b>"]
    by_blog: dict[str, list[Article]] = {}
    for article in articles:
        by_blog.setdefault(article.blog, []).append(article)
    for blog in sorted(by_blog):
        blocks.append(f"<b>{html.escape(blog)}</b>")
        for article in by_blog[blog]:
            entry = (
                f'• <a href="{html.escape(article.url, quote=True)}">'
                f"{html.escape(article.title)}</a>"
            )
            if article.summary:
                entry += f"\n{html.escape(article.summary)}"
            blocks.append(entry)
    return _pack_messages(blocks)


def _pack_messages(blocks: list[str]) -> list[str]:
    messages = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > MAX_MESSAGE_CHARS and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


def send_digest(messages: list[str], token: str, chat_id: str) -> None:
    for message in messages:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=SEND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram send failed: {body}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/telegram.py tests/test_telegram.py
git commit -m "feat: format and send the Telegram digest"
```

---

### Task 7: Lambda handler orchestration

**Files:**
- Create: `src/handler.py`
- Test: `tests/test_handler.py`

**Interfaces:**
- Consumes: everything from Tasks 2–6: `fetch_all_feeds()`, `filter_new()`, `mark_seen()`, `load_config()`/`Config`, `make_client()`, `summarize()`, `format_digest()`, `send_digest()`
- Produces: `lambda_handler(event, context) -> dict` returning `{"new_articles": int, "messages_sent": int}`

- [ ] **Step 1: Write the failing tests**

`tests/test_handler.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'handler'`

- [ ] **Step 3: Write minimal implementation**

`src/handler.py`:

```python
import logging

from config import load_config
from feeds import fetch_all_feeds
from state import filter_new, mark_seen
from summarize import make_client, summarize
from telegram import format_digest, send_digest

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    config = load_config()
    articles = fetch_all_feeds()
    new_articles = filter_new(articles)
    logger.info("Fetched %d articles, %d new", len(articles), len(new_articles))
    if not new_articles:
        return {"new_articles": 0, "messages_sent": 0}

    client = make_client(config.gemini_api_key)
    for article in new_articles:
        article.summary = summarize(client, article)

    messages = format_digest(new_articles)
    send_digest(messages, config.telegram_bot_token, config.telegram_chat_id)
    # Only after a successful send — a failed run must re-deliver tomorrow.
    mark_seen(new_articles)
    return {"new_articles": len(new_articles), "messages_sent": len(messages)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handler.py -v`
Expected: PASS (3 tests). Also run the full suite: `pytest` — everything passes.

- [ ] **Step 5: Commit**

```bash
git add src/handler.py tests/test_handler.py
git commit -m "feat: Lambda handler wiring fetch, diff, summarize, send, mark-seen"
```

---

### Task 8: Local dry-run script

**Files:**
- Create: `local_run.py` (repo root)

**Interfaces:**
- Consumes: `fetch_all_feeds()`, `make_client()`, `summarize()`, `format_digest()`
- Produces: `python local_run.py` — prints the digest for the last 24h of articles to stdout; no DynamoDB, no Telegram, no mark-seen. Uses Gemini only if `GEMINI_API_KEY` is set, otherwise RSS excerpts.

- [ ] **Step 1: Write the script**

`local_run.py`:

```python
"""Print today's digest to stdout without sending or marking anything seen.

Usage:
    python local_run.py                      # summaries = RSS excerpts (no API key needed)
    GEMINI_API_KEY=... python local_run.py   # real Gemini summaries
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "src")

from feeds import fetch_all_feeds  # noqa: E402
from summarize import make_client, summarize  # noqa: E402
from telegram import format_digest  # noqa: E402


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = [
        a for a in fetch_all_feeds() if a.published and a.published >= cutoff
    ]
    if not articles:
        print("No articles published in the last 24 hours.")
        return
    api_key = os.environ.get("GEMINI_API_KEY")
    client = make_client(api_key) if api_key else None
    for article in articles:
        article.summary = summarize(client, article)
    for message in format_digest(articles):
        print(message)
        print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs against the live feeds**

Run: `.venv/bin/python local_run.py`
Expected: an HTML-formatted digest of the last 24h printed to stdout (or "No articles published in the last 24 hours." on a quiet day). No network calls to Telegram or AWS.

- [ ] **Step 3: Run the full test suite**

Run: `pytest`
Expected: all tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add local_run.py
git commit -m "feat: local dry-run script printing the digest to stdout"
```

---

### Task 9: SAM template and README

**Files:**
- Create: `template.yaml`
- Create: `README.md`

**Interfaces:**
- Consumes: `src/handler.lambda_handler` (Task 7), `src/requirements.txt` (Task 1), SSM parameter names (Task 4)
- Produces: deployable stack — Lambda `aws-infra-feed-digest`, DynamoDB table (name exported to the function as `TABLE_NAME`), EventBridge schedule `cron(50 23 * * ? *)`

- [ ] **Step 1: Write the SAM template**

`template.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Daily digest of 14 AWS blogs, summarized by Gemini, sent to Telegram.

Resources:
  DigestFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aws-infra-feed-digest
      CodeUri: src/
      Handler: handler.lambda_handler
      Runtime: python3.13
      Timeout: 600
      MemorySize: 256
      Environment:
        Variables:
          TABLE_NAME: !Ref SeenArticlesTable
      Events:
        DailyDigest:
          Type: Schedule
          Properties:
            # 23:50 UTC = 07:50 SGT; digest lands in Telegram by 08:00 SGT.
            Schedule: cron(50 23 * * ? *)
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref SeenArticlesTable
        - Statement:
            - Effect: Allow
              Action: ssm:GetParameter
              Resource: !Sub arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/infra-feed/*

  SeenArticlesTable:
    Type: AWS::DynamoDB::Table
    Properties:
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: guid
          AttributeType: S
      KeySchema:
        - AttributeName: guid
          KeyType: HASH
      TimeToLiveSpecification:
        AttributeName: expires_at
        Enabled: true

Outputs:
  FunctionName:
    Value: !Ref DigestFunction
  TableName:
    Value: !Ref SeenArticlesTable
```

- [ ] **Step 2: Validate the template**

Run: `sam validate --lint`
Expected: `template.yaml is a valid SAM Template`. (If the `sam` CLI is missing: `brew install aws-sam-cli`.)

- [ ] **Step 3: Write the README**

`README.md`:

````markdown
# aws-infra-feed

A Telegram bot that sends one daily digest (8:00 AM SGT) of new articles from
14 AWS blogs, each summarized in 2–3 sentences by Gemini.

## How it works

A single Lambda fires at 23:50 UTC (7:50 AM SGT): it fetches the 14 RSS feeds
(`src/feeds.py`), diffs against a DynamoDB seen-articles table, summarizes new
articles with Gemini (`gemini-3.6-flash`), sends an HTML digest via the
Telegram Bot API, and only then marks the articles as seen — so a failed run
re-delivers tomorrow instead of dropping articles.

## One-time setup

1. **Telegram bot:** message [@BotFather](https://t.me/BotFather), `/newbot`,
   save the token.
2. **Chat ID:** send your new bot any message, then run
   `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` and read
   `.result[0].message.chat.id`.
3. **Gemini API key:** create one at https://aistudio.google.com/apikey.
4. **Store the secrets** (region must match where you deploy):

   ```bash
   aws ssm put-parameter --name /infra-feed/telegram-bot-token --type SecureString --value '<TOKEN>'
   aws ssm put-parameter --name /infra-feed/telegram-chat-id   --type SecureString --value '<CHAT_ID>'
   aws ssm put-parameter --name /infra-feed/gemini-api-key     --type SecureString --value '<KEY>'
   ```

## Deploy

```bash
sam build
sam deploy --guided   # first time; plain `sam deploy` afterwards
```

Send yourself a digest right now:

```bash
aws lambda invoke --function-name aws-infra-feed-digest /dev/stdout
```

## Develop

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                 # full test suite, fully offline
.venv/bin/python local_run.py    # print today's digest to stdout, sends nothing
```

Add or remove a blog by editing the `FEEDS` dict in `src/feeds.py`.
````

- [ ] **Step 4: Commit**

```bash
git add template.yaml README.md
git commit -m "feat: SAM template and README with setup/deploy instructions"
```

---

### Task 10: CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

**Interfaces:**
- Consumes: the finished repo layout from Tasks 1–9
- Produces: guidance file for future Claude Code sessions

- [ ] **Step 1: Write CLAUDE.md**

`CLAUDE.md`:

````markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot delivering a daily 8:00 AM SGT digest of new articles from 14 AWS
blogs, summarized by Gemini. One Python 3.13 Lambda (EventBridge cron
`cron(50 23 * * ? *)` — 7:50 AM SGT so the digest arrives by 8:00), deployed
with AWS SAM.

## Commands

```bash
.venv/bin/pytest                                # run all tests (offline; moto mocks AWS)
.venv/bin/pytest tests/test_feeds.py::test_parse_feed_extracts_articles -v   # single test
.venv/bin/python local_run.py                   # dry run: print digest to stdout, send nothing
sam validate --lint                             # check template.yaml
sam build && sam deploy                         # deploy
aws lambda invoke --function-name aws-infra-feed-digest /dev/stdout          # trigger a real digest now
```

Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`

## Architecture

Pipeline in `src/handler.py`: `fetch_all_feeds()` → `filter_new()` (DynamoDB) →
`summarize()` (Gemini) → `format_digest()`/`send_digest()` (Telegram) →
`mark_seen()`.

Invariants that must hold:

- **`mark_seen()` runs only after `send_digest()` succeeds.** A failed run must
  re-deliver tomorrow; duplicates are acceptable, dropped articles are not.
  `tests/test_handler.py::test_failed_send_does_not_mark_seen` guards this.
- A broken feed or Gemini error degrades gracefully (feed skipped / RSS excerpt
  used); only a Telegram send failure fails the run.
- The Gemini model is pinned once as `GEMINI_MODEL` in `src/summarize.py`
  (`gemini-3.6-flash`).

Key facts:

- `src/` is the Lambda package root, so modules import each other top-level
  (`from feeds import ...`, not `from src.feeds import ...`). Tests resolve
  this via `pythonpath = ["src"]` in `pyproject.toml`.
- `src/telegram.py` is a local module, not the `python-telegram-bot` package.
- The 14 blogs live in the `FEEDS` dict in `src/feeds.py`; add/remove blogs there.
- Secrets come from env vars first, then SSM SecureStrings under
  `/infra-feed/` (see `src/config.py`). Nothing sensitive in the repo.
- Runtime deps go in `src/requirements.txt` (bundled by SAM; boto3 excluded —
  the Lambda runtime provides it). Dev/test deps go in `requirements-dev.txt`.
- DynamoDB table stores seen article GUIDs with a 90-day TTL (`expires_at`).
````

- [ ] **Step 2: Run the full suite one last time**

Run: `pytest`
Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md for future Claude Code sessions"
```
