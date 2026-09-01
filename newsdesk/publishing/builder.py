"""Shared publication article builder."""

from __future__ import annotations

from ..classification import (
    ClassificationResult,
    StoryClassifier,
)
from ..decisions import (
    DecisionEngine,
    DecisionResult,
)

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .base import BaseFormatter


if TYPE_CHECKING:
    from ..editorial import EditorialEngine


@dataclass(slots=True)
class BuiltArticle:
    """Cleaned and editorially prepared story content."""

    title: str
    summary: str = ""
    paragraphs: list[str] = field(default_factory=list)

    source: str = ""
    location: str = ""
    category: str = ""
    published: str = ""
    source_url: str = ""

    classification: ClassificationResult | None = None
    decision: DecisionResult | None = None

    def content_sections(
        self,
        *,
        include_title: bool = True,
        include_summary: bool = True,
    ) -> list[str]:
        sections: list[str] = []

        if include_title and self.title:
            sections.append(self.title)

        if include_summary and self.summary:
            sections.append(self.summary)

        sections.extend(self.paragraphs)

        return sections

    def footer_lines(self) -> list[str]:
        """Return publication attribution details."""

        footer: list[str] = []

        if self.source:
            footer.append(f"Source: {self.source}")

        if self.location:
            footer.append(f"Area: {self.location}")

        if self.category:
            footer.append(f"Category: {self.category}")

        if self.published:
            footer.append(f"Published: {self.published}")

        return footer

    @property
    def full_text(self) -> str:
        return "\n\n".join(self.content_sections())

    @property
    def has_content(self) -> bool:
        return bool(self.summary or self.paragraphs)


class ArticleBuilder(BaseFormatter):
    """
    Build the authoritative publishable article from a Story.

    Processing order:

    1. Extract content from the Story.
    2. Remove scraper artefacts and duplicate content.
    3. Apply conservative editorial house-style improvements.
    4. Return one BuiltArticle for all publishing channels.
    """

    SCRAPE_NOISE_LINES = {
        "main article content",
        "article content",
        "main content",
        "news",
        "latest news",
        "published:",
        "share this article",
        "share this page",
        "related articles",
        "related news",
        "subscribe",
        "sign up",
        "advertisement",
    }

    IMAGE_FILENAME_PATTERN = re.compile(
        r"""
        ^
        [^\n]*
        \.(?:jpg|jpeg|png|gif|webp|svg)
        $
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    DATE_FILENAME_PATTERN = re.compile(
        r"""
        ^
        \d{6,8}
        [-_]
        [a-z0-9_-]+
        \.(?:jpg|jpeg|png|gif|webp)
        $
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    WHITESPACE_PATTERN = re.compile(r"[ \t]+")
    EXCESS_LINE_BREAKS_PATTERN = re.compile(r"\n{3,}")

    def __init__(
        self,
        editor: EditorialEngine | None = None,
        classifier: StoryClassifier | None = None,
        decision_engine: DecisionEngine | None = None,
        *,
        apply_editorial: bool = True,
    ) -> None:
        """
        Initialise the builder.

        The editorial import is deliberately performed here rather than at
        module level to avoid a circular import between BuiltArticle and
        EditorialEngine.
        """

        self.apply_editorial = apply_editorial

        if editor is not None:
            self.editor = editor
        elif apply_editorial:
            from ..editorial import EditorialEngine

            self.editor = EditorialEngine()
        else:
            self.editor = None

        self.classifier = classifier or StoryClassifier()
        self.decision_engine = decision_engine or DecisionEngine()

    def build(self, story: Any) -> BuiltArticle:
        """Create a cleaned and editorially prepared article."""

        raw_title = self.title(story)
        raw_summary = self.summary(story)

        article = BuiltArticle(
            title=self._clean_title(raw_title) or "Untitled story",
            summary=self._clean_summary(
                raw_summary,
                raw_title,
            ),
            paragraphs=self._clean_paragraphs(
                self.article_paragraphs(story),
                title=raw_title,
                summary=raw_summary,
            ),
            source=self._clean_single_line(
                self.source(story)
            ),
            location=self._clean_single_line(
                self.location(story)
            ),
            category=self._clean_single_line(
                self.category(story)
            ),
            published=self._story_value(
                story,
                "published",
                "published_at",
                "publication_date",
                "date",
            ),
            source_url=self._story_value(
                story,
                "source_url",
                "url",
                "link",
            ),
        )

        return self._enrich(article)

    def _enrich(
        self,
        article: BuiltArticle,
    ) -> BuiltArticle:
        """Apply editorial, classification and decision enrichment."""

        if self.editor is not None:
            article = self.editor.edit(article)

        article.classification = self.classifier.classify_text(
            title=article.title,
            summary=article.summary,
            body="\n\n".join(article.paragraphs),
            location=article.location,
        )

        article.decision = self.decision_engine.decide(article)

        return article

    def _clean_title(self, value: Any) -> str:
        title = self._clean_single_line(value)

        title = re.sub(
            r"^(?:news|latest news|press release)"
            r"\s*[:\-–—]\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

        return title.strip(" -–—")

    def _clean_summary(
        self,
        value: Any,
        title: Any,
    ) -> str:
        summary = self._clean_single_line(value)
        clean_title = self._clean_title(title)

        if not summary:
            return ""

        if (
            self._normalise_for_comparison(summary)
            == self._normalise_for_comparison(clean_title)
        ):
            return ""

        if self._is_scrape_noise(summary):
            return ""

        return summary

    def _clean_paragraphs(
        self,
        paragraphs: list[str],
        *,
        title: Any,
        summary: Any,
    ) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        title_key = self._normalise_for_comparison(
            self._clean_title(title)
        )

        summary_key = self._normalise_for_comparison(
            self._clean_summary(summary, title)
        )

        for raw_paragraph in paragraphs:
            paragraph = self._clean_paragraph(
                raw_paragraph
            )

            if not paragraph:
                continue

            if self._is_scrape_noise(paragraph):
                continue

            comparison_key = (
                self._normalise_for_comparison(
                    paragraph
                )
            )

            if not comparison_key:
                continue

            if comparison_key in {
                title_key,
                summary_key,
            }:
                continue

            if comparison_key in seen:
                continue

            seen.add(comparison_key)
            cleaned.append(paragraph)

        return cleaned

    def _clean_paragraph(self, value: Any) -> str:
        paragraph = str(value or "").strip()

        if not paragraph:
            return ""

        paragraph = paragraph.replace(
            "\r\n",
            "\n",
        )
        paragraph = paragraph.replace(
            "\r",
            "\n",
        )

        paragraph = self.WHITESPACE_PATTERN.sub(
            " ",
            paragraph,
        )

        paragraph = (
            self.EXCESS_LINE_BREAKS_PATTERN.sub(
                "\n\n",
                paragraph,
            )
        )

        lines = [
            line.strip()
            for line in paragraph.splitlines()
            if line.strip()
        ]

        paragraph = " ".join(lines)

        return paragraph.strip()

    def _clean_single_line(self, value: Any) -> str:
        text = str(value or "").strip()

        if not text:
            return ""

        return " ".join(text.split())

    def _story_value(
        self,
        story: Any,
        *attribute_names: str,
    ) -> str:
        """
        Return the first populated Story attribute from a list of names.

        This supports Story implementations that use slightly different
        attribute names for publication dates and source URLs.
        """

        for attribute_name in attribute_names:
            value = getattr(
                story,
                attribute_name,
                "",
            )

            cleaned = self._clean_single_line(value)

            if cleaned:
                return cleaned

        return ""

    def _is_scrape_noise(self, text: str) -> bool:
        normalised = self._normalise_for_comparison(
            text
        )

        if not normalised:
            return True

        if normalised in self.SCRAPE_NOISE_LINES:
            return True

        if self.IMAGE_FILENAME_PATTERN.fullmatch(
            text.strip()
        ):
            return True

        if self.DATE_FILENAME_PATTERN.fullmatch(
            text.strip()
        ):
            return True

        noise_prefixes = (
            "subscribe to ",
            "sign up to ",
            "sign up for ",
            "follow us on ",
            "read more:",
            "related:",
            "image:",
            "photo:",
            "picture:",
            "copyright:",
        )

        if normalised.startswith(noise_prefixes):
            return True

        return False

    @staticmethod
    def _normalise_for_comparison(
        value: Any,
    ) -> str:
        text = str(value or "").casefold()
        text = re.sub(r"[^\w\s]", "", text)

        return " ".join(text.split())