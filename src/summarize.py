import html
import logging
import re

from google import genai

from models import Article

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.6-flash"
MAX_CONTENT_CHARS = 30_000

PROMPT = (
    "Summarize this AWS blog post in 2-3 plain sentences for a daily digest. "
    "Focus on what changed or what the reader can now do. "
    "No preamble, no markdown, no bullet points.\n\n"
    "Title: {title}\n\n{content}"
)


def make_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def summarize(client, article: Article) -> str:
    if client is None:
        return _strip_html(article.excerpt)
    try:
        content = _strip_html(article.content)[:MAX_CONTENT_CHARS]
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=PROMPT.format(title=article.title, content=content),
        )
        summary = (response.text or "").strip()
        if summary:
            return summary
        logger.warning("Empty Gemini response for %s", article.url)
    except Exception:
        logger.warning(
            "Gemini failed for %s; falling back to excerpt", article.url, exc_info=True
        )
    return _strip_html(article.excerpt)


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", html.unescape(text))
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    return text.strip()
