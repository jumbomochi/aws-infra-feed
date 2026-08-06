# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot delivering a daily 8:00 AM SGT digest of new articles from 14 AWS
blogs, summarized by Gemini. One Python 3.13 Lambda (EventBridge cron
`cron(50 23 * * ? *)` — 7:50 AM SGT so the digest arrives by 8:00), deployed
with AWS SAM.

## Commands

```bash
.venv/bin/pytest                                # run all tests (offline; moto mocks AWS)
.venv/bin/pytest tests/test_feeds.py::test_parse_feed_extracts_articles -v   # single test
.venv/bin/python local_run.py                   # dry run: print digest to stdout, send nothing
sam validate --lint                             # check template.yaml
sam build && sam deploy                         # deploy
aws lambda invoke --function-name aws-infra-feed-digest /dev/stdout          # trigger a real digest now
```

Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`

## Architecture

Pipeline in `src/handler.py`: `fetch_all_feeds()` → `filter_new()` (DynamoDB) →
`summarize()` (Gemini) → `format_digest()`/`send_digest()` (Telegram) →
`mark_seen()`.

Invariants that must hold:

- **`mark_seen()` runs only after `send_digest()` succeeds.** A failed run must
  re-deliver tomorrow; duplicates are acceptable, dropped articles are not.
  `tests/test_handler.py::test_failed_send_does_not_mark_seen` guards this.
- A broken feed or Gemini error degrades gracefully (feed skipped / RSS excerpt
  used); only a Telegram send failure fails the run.
- The Gemini model is pinned once as `GEMINI_MODEL` in `src/summarize.py`
  (`gemini-3.6-flash`).

Key facts:

- `src/` is the Lambda package root, so modules import each other top-level
  (`from feeds import ...`, not `from src.feeds import ...`). Tests resolve
  this via `pythonpath = ["src"]` in `pyproject.toml`.
- `src/telegram.py` is a local module, not the `python-telegram-bot` package.
- The 14 blogs live in the `FEEDS` dict in `src/feeds.py`; add/remove blogs there.
- Secrets come from env vars first, then SSM SecureStrings under
  `/infra-feed/` (see `src/config.py`). Nothing sensitive in the repo.
- Runtime deps go in `src/requirements.txt` (bundled by SAM; boto3 excluded —
  the Lambda runtime provides it). Dev/test deps go in `requirements-dev.txt`.
- DynamoDB table stores seen article GUIDs with a 90-day TTL (`expires_at`).
- `format_digest` caps summaries at `MAX_SUMMARY_CHARS` (700, pre-escape) and packs
  messages so a blog header always shares a message with its first article.
- The handler processes at most `MAX_ARTICLES_PER_RUN` (60) newest articles per
  run — Gemini takes ~5s/article, so an uncapped spike (or first-run backlog)
  times out the 600s Lambda. The remainder stays unseen and drains next run.
- Deployed to account 759650489076 (`vsc-sso` profile), ap-southeast-1, stack
  `aws-infra-feed`. A fresh deploy needs a one-time bootstrap marking the feed
  backlog seen (fetch + mark_seen without sending), or the first runs will each
  cap out on stale articles.
