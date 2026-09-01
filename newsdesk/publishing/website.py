"""Website publication formatter."""

from __future__ import annotations

from typing import Any

from .builder import ArticleBuilder


class WebsiteFormatter:
    """Create complete website-ready article copy."""

    FALLBACK_TEXT = (
        "Further information was not available in the supplied "
        "source material."
    )

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
    ) -> None:
        self.builder = builder or ArticleBuilder()

    def format(self, story: Any) -> str:
        article = self.builder.build(story)

        sections: list[str] = []

        if article.title:
            sections.append(article.title)

        if article.summary:
            sections.append(article.summary)

        if article.paragraphs:
            sections.extend(article.paragraphs)
        elif not article.summary:
            sections.append(self.FALLBACK_TEXT)

        attribution = self._build_attribution(article)

        if attribution:
            sections.append(attribution)

        return "\n\n".join(
            section.strip()
            for section in sections
            if section and section.strip()
        )

    @staticmethod
    def _build_attribution(article) -> str:
        """
        Build a concise website attribution block.

        Category is intentionally excluded from the visible article footer
        because it is normally handled by the website CMS.
        """

        details: list[str] = []

        if article.source:
            details.append(f"Source: {article.source}")

        if article.location:
            details.append(f"Area: {article.location}")

        if article.published:
            details.append(f"Published: {article.published}")

        return " | ".join(details)