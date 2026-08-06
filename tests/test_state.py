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


def test_mark_seen_allows_duplicate_guids_in_one_batch(seen_table, make_article):
    articles = [
        make_article(guid="dup", title="First"),
        make_article(guid="dup", title="Second"),
    ]
    mark_seen(articles)
    item = seen_table.get_item(Key={"guid": "dup"})["Item"]
    assert item["guid"] == "dup"
