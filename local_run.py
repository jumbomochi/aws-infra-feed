"""Print today's digest to stdout without sending or marking anything seen.

Usage:
    python local_run.py                      # summaries = RSS excerpts (no API key needed)
    GEMINI_API_KEY=... python local_run.py   # real Gemini summaries
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "src")

from feeds import fetch_all_feeds  # noqa: E402
from summarize import make_client, summarize  # noqa: E402
from telegram import format_digest  # noqa: E402


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = [
        a for a in fetch_all_feeds() if a.published and a.published >= cutoff
    ]
    if not articles:
        print("No articles published in the last 24 hours.")
        return
    api_key = os.environ.get("GEMINI_API_KEY")
    client = make_client(api_key) if api_key else None
    for article in articles:
        article.summary = summarize(client, article)
    for message in format_digest(articles):
        print(message)
        print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
