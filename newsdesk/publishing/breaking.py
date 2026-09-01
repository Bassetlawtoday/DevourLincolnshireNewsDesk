"""Breaking-news publication formatter."""

from __future__ import annotations

from typing import Any

from .builder import ArticleBuilder
from .base import BaseFormatter


class BreakingNewsFormatter:
    """Create restrained breaking-news copy."""

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
    ) -> None:
        self.builder = builder or ArticleBuilder()

    def format(self, story: Any) -> str:
        article = self.builder.build(story)

        summary = article.summary

        if not summary and article.paragraphs:
            summary = article.paragraphs[0]

        summary = BaseFormatter.truncate_words(
            summary,
            55,
        )

        sections = [
            "🚨 BREAKING NEWS",
            article.title,
        ]

        if summary:
            sections.append(summary)

        return "\n\n".join(sections)