"""Publishing metadata formatter."""

from __future__ import annotations

import re
from typing import Any

from .builder import ArticleBuilder
from .base import BaseFormatter


try:
    from ..constants import (
        SEO_TITLE_LENGTH,
        META_DESCRIPTION_LENGTH,
    )
except ImportError:
    SEO_TITLE_LENGTH = 60
    META_DESCRIPTION_LENGTH = 160


class MetadataFormatter(BaseFormatter):
    """Create SEO and publishing metadata."""

    STOP_WORDS = {
        "about",
        "after",
        "again",
        "against",
        "being",
        "could",
        "from",
        "have",
        "into",
        "more",
        "news",
        "nottinghamshire",
        "police",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "with",
        "were",
        "will",
        "would",
    }

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
    ) -> None:
        self.builder = builder or ArticleBuilder()

    def seo_title(self, title: str) -> str:
        return self.truncate(
            title,
            SEO_TITLE_LENGTH,
        )

    def meta_description(self, text: str) -> str:
        return self.truncate(
            text,
            META_DESCRIPTION_LENGTH,
        )

    def slug(self, title: str) -> str:
        value = self.clean(title).lower()

        value = re.sub(
            r"[^a-z0-9]+",
            "-",
            value,
        )

        return value.strip("-")

    def tags(self, text: str) -> list[str]:
        words = re.findall(
            r"[A-Za-z][A-Za-z'-]{3,}",
            self.clean(text).lower(),
        )

        tags: list[str] = []

        for word in words:
            word = word.strip("-'")

            if not word:
                continue

            if word in self.STOP_WORDS:
                continue

            if word not in tags:
                tags.append(word)

            if len(tags) == 10:
                break

        return tags

    def keywords(self, text: str) -> list[str]:
        return self.tags(text)

    def image_caption(self, story: Any) -> str:
        article = self.builder.build(story)
        caption = article.title

        if article.location:
            caption += f" — {article.location}"

        if article.source:
            caption += (
                f". Image/source: {article.source}"
            )

        return caption