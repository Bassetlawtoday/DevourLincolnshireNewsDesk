"""Local editorial draft storage for Devour News App Publishing.

This module does not publish to the cloud or modify Social Desk data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


DEFAULT_PATH = Path("data") / "app_publishing" / "drafts.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AppArticle:
    article_id: str = field(default_factory=lambda: uuid4().hex)
    source_identity: str = ""
    title: str = ""
    body: str = ""
    original_body: str = ""
    source: str = ""
    source_url: str = ""
    author: str = ""
    image_url: str = ""
    image_local_path: str = ""
    image_caption: str = ""
    image_credit: str = ""
    county: str = "Lincolnshire"
    areas: list[str] = field(default_factory=list)
    category: str = ""
    notify_readers: bool = False
    notification_type: str = "Breaking news"
    notification_message: str = ""
    status: str = "draft"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def word_count(self) -> int:
        return len(self.body.split())

    @classmethod
    def from_dict(cls, value: dict) -> "AppArticle":
        allowed = cls.__dataclass_fields__
        return cls(**{key: item for key, item in value.items() if key in allowed})


class AppArticleStore:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)

    def load(self) -> list[AppArticle]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
            raise ValueError("Invalid App Publishing draft storage")
        return [AppArticle.from_dict(row) for row in payload["articles"]]

    def save(self, articles: list[AppArticle]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "articles": [asdict(article) for article in articles]}
        fd, temp_path = tempfile.mkstemp(
            prefix=".app-drafts-", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def upsert(self, article: AppArticle) -> None:
        articles = self.load()
        article.updated_at = _now()
        for index, existing in enumerate(articles):
            if existing.article_id == article.article_id:
                articles[index] = article
                break
        else:
            articles.append(article)
        self.save(articles)

    def stage_story(self, story, *, source_identity: str) -> tuple[AppArticle, bool]:
        """Stage once; never overwrite edits already made by an editor."""
        if not source_identity.strip():
            raise ValueError("A stable source identity is required")
        articles = self.load()
        for article in articles:
            if article.source_identity == source_identity:
                return article, False
        body = str(getattr(story, "body", "") or getattr(story, "summary", "") or "")
        article = AppArticle(
            source_identity=source_identity,
            title=str(getattr(story, "title", "") or ""),
            body=body,
            original_body=body,
            source=str(getattr(story, "source", "") or ""),
            source_url=str(getattr(story, "url", "") or ""),
            author=str(getattr(story, "author", "") or ""),
            image_url=str(getattr(story, "image_url", "") or ""),
            image_local_path=str(getattr(story, "image_local_path", "") or ""),
            image_caption=str(getattr(story, "image_caption", "") or ""),
            image_credit=str(getattr(story, "image_credit", "") or ""),
            category=str(getattr(story, "category", "") or ""),
            status="new",
        )
        articles.append(article)
        self.save(articles)
        return article, True
