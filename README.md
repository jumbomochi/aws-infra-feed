# aws-infra-feed

A Telegram bot that sends one daily digest (8:00 AM SGT) of new articles from
14 AWS blogs, each summarized in 2–3 sentences by Gemini.

## How it works

A single Lambda fires at 23:50 UTC (7:50 AM SGT): it fetches the 14 RSS feeds
(`src/feeds.py`), diffs against a DynamoDB seen-articles table, summarizes new
articles with Gemini (`gemini-3.6-flash`), sends an HTML digest via the
Telegram Bot API, and only then marks the articles as seen — so a failed run
re-delivers tomorrow instead of dropping articles.

## One-time setup

1. **Telegram bot:** message [@BotFather](https://t.me/BotFather), `/newbot`,
   save the token.
2. **Chat ID:** send your new bot any message, then run
   `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` and read
   `.result[0].message.chat.id`.
3. **Gemini API key:** create one at https://aistudio.google.com/apikey.
4. **Store the secrets** (region must match where you deploy):

   ```bash
   aws ssm put-parameter --name /infra-feed/telegram-bot-token --type SecureString --value '<TOKEN>'
   aws ssm put-parameter --name /infra-feed/telegram-chat-id   --type SecureString --value '<CHAT_ID>'
   aws ssm put-parameter --name /infra-feed/gemini-api-key     --type SecureString --value '<KEY>'
   ```

## Deploy

```bash
sam build
sam deploy --guided   # first time; plain `sam deploy` afterwards
```

Send yourself a digest right now:

```bash
aws lambda invoke --function-name aws-infra-feed-digest /dev/stdout
```

## Develop

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                 # full test suite, fully offline
.venv/bin/python local_run.py    # print today's digest to stdout, sends nothing
```

Add or remove a blog by editing the `FEEDS` dict in `src/feeds.py`.
