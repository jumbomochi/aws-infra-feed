import boto3
import pytest
from moto import mock_aws

from throwback import THROWBACKS_PER_RUN, create_pool, load_pool_batch, mark_thrown

TABLE = "seen-articles-test"


@pytest.fixture
def pool_table(aws_env, monkeypatch):
    monkeypatch.setenv("TABLE_NAME", TABLE)
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            AttributeDefinitions=[{"AttributeName": "guid", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "guid", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield boto3.resource("dynamodb").Table(TABLE)


def test_create_pool_stores_shuffled_items(pool_table, make_article):
    articles = [make_article(guid=f"g{i}", title=f"Post {i}") for i in range(5)]
    assert create_pool(articles) == 5
    items = pool_table.scan()["Items"]
    assert len(items) == 5
    assert all(item["guid"].startswith("throwback#") for item in items)
    assert {int(item["order"]) for item in items} == {0, 1, 2, 3, 4}
    assert all(item["sent"] is False for item in items)


def test_load_pool_batch_returns_articles_in_order(pool_table, make_article):
    create_pool([make_article(guid=f"g{i}", title=f"Post {i}") for i in range(5)])
    batch = load_pool_batch(limit=3)
    assert len(batch) == 3
    orders = {
        item["guid"]: int(item["order"]) for item in pool_table.scan()["Items"]
    }
    batch_orders = [orders[a.guid] for a in batch]
    assert batch_orders == sorted(batch_orders)
    assert batch_orders == [0, 1, 2]


def test_mark_thrown_removes_from_future_batches(pool_table, make_article):
    create_pool([make_article(guid=f"g{i}") for i in range(4)])
    first = load_pool_batch(limit=3)
    mark_thrown([a.guid for a in first])
    second = load_pool_batch(limit=3)
    assert len(second) == 1
    assert second[0].guid not in {a.guid for a in first}


def test_pool_drains_to_empty(pool_table, make_article):
    create_pool([make_article(guid="only")])
    mark_thrown([a.guid for a in load_pool_batch()])
    assert load_pool_batch() == []


def test_default_batch_size_is_three():
    assert THROWBACKS_PER_RUN == 3
