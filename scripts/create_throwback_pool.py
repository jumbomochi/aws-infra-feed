"""One-time: snapshot the current feed backlog into the throwback pool.

The pool feeds the daily 12:30 SGT throwback post (3 shuffled articles/day)
until it drains. Articles published in the last 12 hours are excluded — the
channel already received them as regular digests.

Usage:
    AWS_PROFILE=<profile> AWS_DEFAULT_REGION=<region> \
    TABLE_NAME=<seen-articles-table> python scripts/create_throwback_pool.py
"""

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "src")

from feeds import fetch_all_feeds  # noqa: E402
from throwback import create_pool  # noqa: E402


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    articles = [
        a
        for a in fetch_all_feeds()
        if not (a.published and a.published >= cutoff)
    ]
    count = create_pool(articles)
    print(f"Created throwback pool with {count} articles.")


if __name__ == "__main__":
    main()
