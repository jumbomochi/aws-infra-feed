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
