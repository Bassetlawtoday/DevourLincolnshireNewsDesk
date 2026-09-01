"""
newsdesk.services.metadata

Metadata generation for NewsDesk stories.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from newsdesk.story import Story


@dataclass(slots=True)
class StoryMetadata:
    """Generated metadata for publishing."""

    slug: str = ""
    seo_title: str = ""
    meta_description: str = ""
    image_prompt: str = ""
    tags: list[str] = field(default_factory=list)


class MetadataService:
    """Generate SEO and publishing metadata for a :class:`Story`."""

    SEO_TITLE_LENGTH = 60
    META_DESCRIPTION_LENGTH = 155
    MAX_TAGS = 10

    _WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
    _WHITESPACE_PATTERN = re.compile(r"\s+")
    _SLUG_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")

    _STOP_WORDS = frozenset(
        {
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
            "other",
            "over",
            "said",
            "that",
            "their",
            "there",
            "these",
            "they",
            "this",
            "through",
            "under",
            "until",
            "where",
            "which",
            "while",
            "with",
            "would",
        }
    )

    def generate(self, story: Story) -> StoryMetadata:
        """Build all publishing metadata for ``story``.

        The method deliberately tolerates empty or ``None``-like values on
        story attributes so metadata generation cannot bring down a collection
        or editing workflow.
        """

        title = self._clean_text(getattr(story, "title", ""))
        summary = self._clean_text(getattr(story, "summary", ""))
        body = self._clean_text(getattr(story, "body", ""))

        description_source = summary or body
        combined_text = " ".join(part for part in (title, summary, body) if part)

        return StoryMetadata(
            slug=self._slugify(title),
            seo_title=self._truncate(title, self.SEO_TITLE_LENGTH),
            meta_description=self._truncate(
                description_source,
                self.META_DESCRIPTION_LENGTH,
            ),
            image_prompt=self._build_image_prompt(title),
            tags=self._extract_tags(combined_text),
        )

    def _truncate(self, text: str, length: int) -> str:
        """Return ``text`` shortened to ``length`` characters.

        Where possible, truncation occurs at a word boundary. The historical
        three-dot suffix is retained for compatibility with existing output.
        """

        cleaned = self._clean_text(text)

        if length <= 0:
            return ""

        if len(cleaned) <= length:
            return cleaned

        if length <= 3:
            return "." * length

        available = length - 3
        shortened = cleaned[:available].rstrip()

        last_space = shortened.rfind(" ")
        if last_space > max(0, available // 2):
            shortened = shortened[:last_space].rstrip()

        return f"{shortened}..."

    def _slugify(self, title: str) -> str:
        """Create a stable, URL-safe slug from ``title``."""

        normalised = unicodedata.normalize("NFKD", self._clean_text(title))
        ascii_title = normalised.encode("ascii", "ignore").decode("ascii")
        slug = self._SLUG_SEPARATOR_PATTERN.sub("-", ascii_title.lower())
        return slug.strip("-")

    def _extract_tags(self, text: str) -> list[str]:
        """Return up to :attr:`MAX_TAGS` unique, useful keyword tags."""

        tags: list[str] = []
        seen: set[str] = set()

        for word in self._iter_tag_candidates(text):
            canonical = word.lower().strip("'-")

            if not canonical or canonical in self._STOP_WORDS:
                continue

            if canonical in seen:
                continue

            seen.add(canonical)
            tags.append(canonical)

            if len(tags) >= self.MAX_TAGS:
                break

        return tags

    def _iter_tag_candidates(self, text: str) -> Iterable[str]:
        return self._WORD_PATTERN.findall(self._clean_text(text))

    def _build_image_prompt(self, title: str) -> str:
        subject = title or "the news story"
        return f"Professional newspaper photograph illustrating: {subject}"

    def _clean_text(self, value: object) -> str:
        if value is None:
            return ""

        return self._WHITESPACE_PATTERN.sub(" ", str(value)).strip()