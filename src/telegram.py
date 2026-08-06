import html
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from models import Article

SGT = timezone(timedelta(hours=8))
MAX_MESSAGE_CHARS = 4000  # headroom under Telegram's 4096 hard limit
MAX_SUMMARY_CHARS = 700  # pre-escape; keeps worst-case escaped entries well under MAX_MESSAGE_CHARS
MAX_ESCAPED_SUMMARY_CHARS = 2800  # post-escape cap; entity expansion can be up to ~5x
SEND_TIMEOUT_SECONDS = 15
SEND_THROTTLE_SECONDS = 1
DEFAULT_RETRY_AFTER_SECONDS = 5


def format_heartbeat(now: datetime | None = None) -> str:
    now = now or datetime.now(SGT)
    return f"<b>AWS Blog Digest — {now:%a %d %b %Y}</b>\n\nNo new articles today."


def format_digest(
    articles: list[Article],
    now: datetime | None = None,
    title: str = "AWS Blog Digest",
) -> list[str]:
    now = now or datetime.now(SGT)
    header = f"<b>{html.escape(title)} — {now:%a %d %b %Y}</b>"
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
        escaped_summary = html.escape(summary)
        if len(escaped_summary) > MAX_ESCAPED_SUMMARY_CHARS:
            escaped_summary = escaped_summary[:MAX_ESCAPED_SUMMARY_CHARS]
            escaped_summary = re.sub(r"&[#0-9a-zA-Z]*$", "", escaped_summary) + "…"
        entry += f"\n{escaped_summary}"
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
    for index, message in enumerate(messages):
        if index > 0:
            time.sleep(SEND_THROTTLE_SECONDS)
        _send_message(message, token, chat_id, allow_retry=True)


def _send_message(message: str, token: str, chat_id: str, allow_retry: bool) -> None:
    # Never let requests' exception messages or raise_for_status() escape this
    # function: both embed the request URL, which contains the bot token, and
    # this function's errors end up in CloudWatch logs.
    try:
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
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram send failed: {type(exc).__name__}") from None

    if response.status_code == 429:
        if not allow_retry:
            raise RuntimeError(
                f"Telegram send failed: HTTP 429 {response.text[:200]}"
            )
        body = response.json()
        retry_after = (body.get("parameters") or {}).get(
            "retry_after", DEFAULT_RETRY_AFTER_SECONDS
        )
        time.sleep(retry_after)
        _send_message(message, token, chat_id, allow_retry=False)
        return

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram send failed: HTTP {response.status_code} {response.text[:200]}"
        )

    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram send failed: {body}")
