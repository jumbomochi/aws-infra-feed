from types import SimpleNamespace

from summarize import GEMINI_MODEL, summarize


class FakeModels:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append({"model": model, "contents": contents})
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


class FakeClient:
    def __init__(self, text=None, error=None):
        self.models = FakeModels(text=text, error=error)


def test_uses_gemini_summary(make_article):
    client = FakeClient(text="  A tidy summary. ")
    article = make_article(content="<p>Long <b>body</b> here</p>")
    assert summarize(client, article) == "A tidy summary."
    call = client.models.calls[0]
    assert call["model"] == GEMINI_MODEL
    assert "Long body here" in call["contents"]
    assert "<b>" not in call["contents"]


def test_falls_back_to_excerpt_on_gemini_error(make_article):
    client = FakeClient(error=RuntimeError("quota"))
    article = make_article(excerpt="Short &amp; sweet <em>excerpt</em>.")
    assert summarize(client, article) == "Short & sweet excerpt."


def test_falls_back_to_excerpt_on_empty_response(make_article):
    client = FakeClient(text="")
    article = make_article(excerpt="Plain excerpt.")
    assert summarize(client, article) == "Plain excerpt."


def test_none_client_uses_excerpt(make_article):
    article = make_article(excerpt="Plain excerpt.")
    assert summarize(None, article) == "Plain excerpt."


def test_model_is_pinned():
    assert GEMINI_MODEL == "gemini-3.6-flash"


def test_strip_html_preserves_paragraph_boundaries(make_article):
    article = make_article(
        excerpt="<p>First paragraph ends here.</p><p>Second starts here.</p>"
    )
    assert summarize(None, article) == "First paragraph ends here. Second starts here."
