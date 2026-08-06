from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    guid: str
    title: str
    url: str
    blog: str
    excerpt: str
    content: str
    published: datetime | None = None
    summary: str = ""
