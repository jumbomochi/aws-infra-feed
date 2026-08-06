import calendar
import logging
from datetime import datetime, timezone

import feedparser
import requests

from models import Article

logger = logging.getLogger(__name__)

FEEDS = {
    "AWS News": "https://aws.amazon.com/blogs/aws/feed/",
    "Architecture": "https://aws.amazon.com/blogs/architecture/feed/",
    "Big Data": "https://aws.amazon.com/blogs/big-data/feed/",
    "Compute": "https://aws.amazon.com/blogs/compute/feed/",
    "Containers": "https://aws.amazon.com/blogs/containers/feed/",
    "Database": "https://aws.amazon.com/blogs/database/feed/",
    "Developer Tools": "https://aws.amazon.com/blogs/developer/feed/",
    "DevOps": "https://aws.amazon.com/blogs/devops/feed/",
    "Machine Learning": "https://aws.amazon.com/blogs/machine-learning/feed/",
    "Management & Governance": "https://aws.amazon.com/blogs/mt/feed/",
    "Public Sector": "https://aws.amazon.com/blogs/publicsector/feed/",
    "Quantum Computing": "https://aws.amazon.com/blogs/quantum-computing/feed/",
    "Security": "https://aws.amazon.com/blogs/security/feed/",
    "Storage": "https://aws.amazon.com/blogs/storage/feed/",
}

FETCH_TIMEOUT_SECONDS = 15
USER_AGENT = "aws-infra-feed/1.0 (personal digest bot)"


def parse_feed(blog: str, xml: bytes) -> list[Article]:
    parsed = feedparser.parse(xml)
    articles = []
    for entry in parsed.entries:
        guid = entry.get("id") or entry.get("link")
        if not guid:
            continue
        excerpt = entry.get("summary", "")
        content = entry.content[0].value if entry.get("content") else excerpt
        published = None
        if entry.get("published_parsed"):
            published = datetime.fromtimestamp(
                calendar.timegm(entry.published_parsed), tz=timezone.utc
            )
        articles.append(
            Article(
                guid=guid,
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                blog=blog,
                excerpt=excerpt,
                content=content,
                published=published,
            )
        )
    return articles


def fetch_all_feeds(feeds: dict[str, str] = FEEDS) -> list[Article]:
    articles = []
    for blog, url in feeds.items():
        try:
            response = requests.get(
                url,
                timeout=FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            articles.extend(parse_feed(blog, response.content))
        except Exception:
            logger.warning("Skipping feed %s (%s)", blog, url, exc_info=True)
    return articles
