import os
import random

import boto3
from boto3.dynamodb.conditions import Attr

from models import Article

THROWBACKS_PER_RUN = 3
POOL_PREFIX = "throwback#"
MAX_STORED_CONTENT_CHARS = 30_000


def _table():
    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def create_pool(articles: list[Article]) -> int:
    """One-time snapshot: store articles as a shuffled throwback pool.

    Pool items share the seen-articles table under a `throwback#` key prefix
    and carry no `expires_at`, so the table's TTL never trims the pool.
    """
    shuffled = list(articles)
    random.shuffle(shuffled)
    table = _table()
    with table.batch_writer(overwrite_by_pkeys=["guid"]) as batch:
        for order, article in enumerate(shuffled):
            batch.put_item(
                Item={
                    "guid": f"{POOL_PREFIX}{article.guid}",
                    "order": order,
                    "title": article.title,
                    "url": article.url,
                    "blog": article.blog,
                    "excerpt": article.excerpt,
                    "content": article.content[:MAX_STORED_CONTENT_CHARS],
                    "sent": False,
                }
            )
    return len(shuffled)


def load_pool_batch(limit: int = THROWBACKS_PER_RUN) -> list[Article]:
    table = _table()
    items = []
    scan_kwargs = {
        "FilterExpression": Attr("guid").begins_with(POOL_PREFIX)
        & Attr("sent").eq(False)
    }
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response["Items"])
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    items.sort(key=lambda item: int(item["order"]))
    return [
        Article(
            guid=item["guid"],
            title=item["title"],
            url=item["url"],
            blog=item["blog"],
            excerpt=item.get("excerpt", ""),
            content=item.get("content", ""),
        )
        for item in items[:limit]
    ]


def mark_thrown(guids: list[str]) -> None:
    table = _table()
    for guid in guids:
        table.update_item(
            Key={"guid": guid},
            UpdateExpression="SET sent = :sent",
            ExpressionAttributeValues={":sent": True},
        )
