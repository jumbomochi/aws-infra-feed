import logging
from datetime import datetime, timezone

from config import load_config
from feeds import fetch_all_feeds
from state import filter_new, mark_seen
from summarize import make_client, summarize
from telegram import format_digest, format_heartbeat, send_digest

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Summarizing takes ~5s/article; 60 keeps the worst case well inside the
# 600s Lambda timeout. Uncapped articles stay unseen and roll into the
# next run, so a spike drains over days instead of timing out forever.
MAX_ARTICLES_PER_RUN = 60

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def lambda_handler(event, context):
    config = load_config()
    articles = fetch_all_feeds()
    new_articles = filter_new(articles)
    logger.info("Fetched %d articles, %d new", len(articles), len(new_articles))
    if not new_articles:
        # Heartbeat: silence would be indistinguishable from a broken bot.
        send_digest(
            [format_heartbeat()], config.telegram_bot_token, config.telegram_chat_id
        )
        return {"new_articles": 0, "messages_sent": 1}
    if len(new_articles) > MAX_ARTICLES_PER_RUN:
        logger.info(
            "Capping run to the newest %d of %d new articles",
            MAX_ARTICLES_PER_RUN,
            len(new_articles),
        )
        new_articles = sorted(
            new_articles, key=lambda a: a.published or _EPOCH, reverse=True
        )[:MAX_ARTICLES_PER_RUN]

    client = make_client(config.gemini_api_key)
    for article in new_articles:
        article.summary = summarize(client, article)

    messages = format_digest(new_articles)
    send_digest(messages, config.telegram_bot_token, config.telegram_chat_id)
    # Only after a successful send — a failed run must re-deliver tomorrow.
    mark_seen(new_articles)
    return {"new_articles": len(new_articles), "messages_sent": len(messages)}
