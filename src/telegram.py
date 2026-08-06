import html
from datetime import datetime, timedelta, timezone

import requests

from models import Article

SGT = timezone(timedelta(hours=8))
MAX_MESSAGE_CHARS = 4000  # headroom under Telegram's 4096 hard limit
MAX_SUMMARY_CHARS = 700  # pre-escape; keeps worst-case escaped entries well under MAX_MESSAGE_CHARS
SEND_TIMEOUT_SECONDS = 15


def format_digest(articles: list[Article], now: datetime | None = None) -> list[str]:
    now = now or datetime.now(SGT)
    header = f"<b>AWS Blog Digest — {now:%a %d %b %Y}</b>"
    by_blog: dict[str, list[Article]] = {}
    for article in articles:
        by_blog.setdefault(article.blog, []).append(article)
    groups = []
    for blog in sorted(by_blog):
        blog_header = f"<b>{html.escape(blog)}</b>"
        entries = [_format_entry(a) for a in by_blog[blog]]
        groups.append((blog_header, entries))
    return _pack_messages(header, groups)


def _format_entry(article: Article) -> str:
    entry = (
        f'• <a href="{html.escape(article.url, quote=True)}">'
        f"{html.escape(article.title)}</a>"
    )
    summary = article.summary
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 1].rstrip() + "…"
    if summary:
        entry += f"\n{html.escape(summary)}"
    return entry


def _pack_messages(header: str, groups: list[tuple[str, list[str]]]) -> list[str]:
    messages = []
    current = header
    for blog_header, entries in groups:
        pending_header = blog_header
        for entry in entries:
            addition = f"{pending_header}\n\n{entry}" if pending_header else entry
            pending_header = None
            candidate = f"{current}\n\n{addition}" if current else addition
            if len(candidate) > MAX_MESSAGE_CHARS and current:
                messages.append(current)
                current = addition
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
