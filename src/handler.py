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
