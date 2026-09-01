"""Newsletter publication formatter."""

from __future__ import annotations

import re
from typing import Any

from .builder import ArticleBuilder


class NewsletterFormatter:
    """Create concise newsletter-ready story copy."""

    DEFAULT_MAX_PARAGRAPHS = 4
    DEFAULT_MAX_LENGTH = 1_800

    QUOTE_PATTERN = re.compile(
        r"""["“‘][^"”’]+["”’]""",
        re.DOTALL,
    )

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
        *,
        max_paragraphs: int = DEFAULT_MAX_PARAGRAPHS,
        max_length: int = DEFAULT_MAX_LENGTH,
    ) -> None:
        self.builder = builder or ArticleBuilder()
        self.max_paragraphs = max(1, int(max_paragraphs))
        self.max_length = max(300, int(max_length))

    def format(self, story: Any) -> str:
        article = self.builder.build(story)

        sections: list[str] = []

        if article.title:
            sections.append(article.title)

        standfirst = self._build_standfirst(
            article.summary,
            article.paragraphs,
        )

        if standfirst:
            sections.append(standfirst)

        body = self._select_body_paragraphs(
            article.paragraphs,
            standfirst=standfirst,
        )

        sections.extend(body)

        if not article.has_content:
            sections.append(
                "Further details were not available in the "
                "supplied source material."
            )

        footer = self._build_footer(article)

        if footer:
            sections.append(footer)

        output = "\n\n".join(
            section.strip()
            for section in sections
            if section and section.strip()
        )

        return self._limit_length(output)

    def _build_standfirst(
        self,
        summary: str,
        paragraphs: list[str],
    ) -> str:
        """Choose a concise opening summary."""

        summary = str(summary or "").strip()

        if summary:
            return summary

        for paragraph in paragraphs:
            paragraph = str(paragraph or "").strip()

            if paragraph:
                return paragraph

        return ""

    def _select_body_paragraphs(
        self,
        paragraphs: list[str],
        *,
        standfirst: str,
    ) -> list[str]:
        """
        Select a compact newsletter body.

        Priority is given to:
        1. early factual paragraphs
        2. one useful direct quote
        3. appeal or public-information details
        """

        selected: list[str] = []
        deferred_quote: str = ""

        standfirst_key = self._comparison_key(standfirst)

        for paragraph in paragraphs:
            paragraph = str(paragraph or "").strip()

            if not paragraph:
                continue

            if self._comparison_key(paragraph) == standfirst_key:
                continue

            if self._contains_quote(paragraph):
                if not deferred_quote:
                    deferred_quote = paragraph
                continue

            selected.append(paragraph)

            if len(selected) >= self.max_paragraphs:
                break

        if (
            deferred_quote
            and len(selected) < self.max_paragraphs
        ):
            selected.append(deferred_quote)

        elif (
            deferred_quote
            and selected
            and not any(
                self._contains_quote(paragraph)
                for paragraph in selected
            )
        ):
            selected[-1] = deferred_quote

        return selected[: self.max_paragraphs]

    def _build_footer(self, article: Any) -> str:
        details: list[str] = []

        if article.location:
            details.append(f"Area: {article.location}")

        if article.category:
            details.append(f"Category: {article.category}")

        if article.source:
            details.append(f"Source: {article.source}")

        return " | ".join(details)

    def _limit_length(self, text: str) -> str:
        """Trim unusually long newsletter output cleanly."""

        text = str(text or "").strip()

        if len(text) <= self.max_length:
            return text

        shortened = text[: self.max_length - 1]

        paragraph_break = shortened.rfind("\n\n")

        if paragraph_break > self.max_length // 2:
            shortened = shortened[:paragraph_break]
        else:
            sentence_break = max(
                shortened.rfind(". "),
                shortened.rfind("! "),
                shortened.rfind("? "),
            )

            if sentence_break > self.max_length // 2:
                shortened = shortened[: sentence_break + 1]

        return shortened.rstrip() + "…"

    def _contains_quote(self, text: str) -> bool:
        return bool(
            self.QUOTE_PATTERN.search(
                str(text or "")
            )
        )

    @staticmethod
    def _comparison_key(value: Any) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^\w\s]", "", text)

        return " ".join(text.split())