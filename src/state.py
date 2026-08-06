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
