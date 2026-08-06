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
