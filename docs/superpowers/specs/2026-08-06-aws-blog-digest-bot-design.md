# AWS Blog Digest Bot — Design

**Date:** 2026-08-06
**Status:** Approved

## Purpose

A Telegram bot that delivers one daily digest of new articles published on 14 AWS
blogs, each article accompanied by a short LLM-written summary. The digest must be
in the user's Telegram chat by 8:00 AM Singapore time.

## Sources

Each blog is polled via its RSS feed (`<blog-url>/feed/`). The list lives in a
config file (`src/feeds.py`) so adding or removing a blog is a one-line change.

1. https://aws.amazon.com/blogs/aws/ (AWS News Blog)
2. https://aws.amazon.com/blogs/compute/
3. https://aws.amazon.com/blogs/containers/
4. https://aws.amazon.com/blogs/database/
5. https://aws.amazon.com/blogs/storage/
6. https://aws.amazon.com/blogs/architecture/
7. https://aws.amazon.com/blogs/mt/ (Management & Governance)
8. https://aws.amazon.com/blogs/developer/
9. https://aws.amazon.com/blogs/security/
10. https://aws.amazon.com/blogs/machine-learning/
11. https://aws.amazon.com/blogs/big-data/
12. https://aws.amazon.com/blogs/devops/
13. https://aws.amazon.com/blogs/publicsector/
14. https://aws.amazon.com/blogs/quantum-computing/

## Architecture

Single Python 3.13 Lambda, deployed with AWS SAM, triggered by an EventBridge
schedule at **23:50 UTC daily** (7:50 AM SGT — Singapore has no DST, so a fixed
UTC cron is safe). The run takes a minute or two, so the digest lands by 8:00 AM.

Pipeline per run:

```
fetch 14 feeds → diff against seen-articles table → summarize new articles
with Gemini → send Telegram digest → mark articles as seen
```

Alternatives considered and rejected: a two-Lambda hourly-poller/daily-sender
pipeline (unneeded — AWS feeds retain ~20 items, far more than one day's volume)
and Step Functions (overkill at this scale).

## Components

All under `src/`:

- **`feeds.py`** — feed URL list; fetches and parses each feed with `feedparser`.
  A feed that errors or times out is logged and skipped — never fatal to the run.
- **`state.py`** — DynamoDB table keyed by article GUID, 90-day TTL. An article
  is "new" if its GUID is absent from the table.
- **`summarize.py`** — one Gemini call per new article (model `gemini-3.6-flash`,
  set as a single config value) producing a 2–3 sentence summary from the article
  content embedded in the feed entry. On any Gemini error the article ships with
  its RSS excerpt instead — a degraded digest beats a missing one.
- **`telegram.py`** — formats the digest (HTML parse mode; articles grouped by
  blog; each entry is a linked title plus summary) and sends via the Bot API,
  splitting into multiple messages when over Telegram's 4,096-character limit.
- **`handler.py`** — Lambda entrypoint orchestrating the pipeline. Articles are
  marked seen **only after** the digest sends successfully, so a failed run
  simply retries the next day (worst case a duplicate entry, never a silent
  drop). If there are no new articles, no message is sent.

## Configuration & secrets

- Telegram bot token, Telegram chat ID, and Gemini API key are stored in SSM
  Parameter Store as SecureStrings and read at Lambda cold start. Nothing
  sensitive appears in the repo or the SAM template.
- One-time manual setup: create the bot via @BotFather (token), message the bot
  once and capture the chat ID, create a Gemini API key, and put all three into
  Parameter Store.

## Error handling

| Failure | Behavior |
|---|---|
| One feed down / malformed | Skip it, log a warning, digest covers the rest |
| Gemini error on an article | Fall back to the RSS excerpt for that article |
| Telegram send fails | Run fails; nothing marked seen; next run re-delivers |
| Duplicate risk | Partial multi-message send may repeat entries next day — accepted trade-off vs. dropping articles |

## Testing

- `pytest` with saved RSS XML fixtures, `moto` mocking DynamoDB, and mocked
  Gemini/Telegram clients — the full pipeline runs offline.
- A local `--dry-run` entrypoint prints the digest to stdout instead of sending,
  and skips the mark-seen write.

## Cost

Effectively zero: one Lambda invocation/day, DynamoDB and SSM within the free
tier, and Gemini Flash free tier comfortably covers ~10–25 articles/day.
