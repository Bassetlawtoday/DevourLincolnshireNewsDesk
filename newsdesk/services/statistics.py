"""Story statistics calculations for Devour Lincolnshire NewsDesk."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

from newsdesk.story import Story


_WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])(?:[\"'’”)]*)\s+|[.!?]+$")
_PARAGRAPH_RE = re.compile(r"(?:\r?\n)\s*(?:\r?\n)+")


@dataclass(slots=True)
class StoryStatistics:
    """Statistics generated for a story."""

    word_count: int = 0
    character_count: int = 0
    paragraph_count: int = 0
    sentence_count: int = 0
    reading_time: int = 0


class StatisticsService:
    """Calculate publication statistics for a :class:`~newsdesk.story.Story`.

    Reading time is rounded up using approximately 200 words per minute. Empty
    stories return zero sentences, paragraphs and reading time rather than
    reporting artificial minimum values.
    """

    WORDS_PER_MINUTE = 200

    def calculate(self, story: Story) -> StoryStatistics:
        """Return statistics for ``story`` without modifying it.

        ``Story.body`` is expected to be text, but defensive normalisation is
        used so partially populated stories do not break the editorial UI.
        """

        body = self._normalise_body(getattr(story, "body", ""))

        if not body:
            return StoryStatistics()

        word_count = len(_WORD_RE.findall(body))
        character_count = len(body)
        paragraph_count = self._count_paragraphs(body)
        sentence_count = self._count_sentences(body)
        reading_time = (
            max(1, math.ceil(word_count / self.WORDS_PER_MINUTE))
            if word_count
            else 0
        )

        return StoryStatistics(
            word_count=word_count,
            character_count=character_count,
            paragraph_count=paragraph_count,
            sentence_count=sentence_count,
            reading_time=reading_time,
        )

    @staticmethod
    def _normalise_body(value: Any) -> str:
        """Convert a body value to clean text while preserving paragraphs."""

        if value is None:
            return ""

        text = value if isinstance(value, str) else str(value)
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()

    @staticmethod
    def _count_paragraphs(body: str) -> int:
        """Count non-empty paragraphs separated by one or more blank lines."""

        return sum(1 for part in _PARAGRAPH_RE.split(body) if part.strip())

    @staticmethod
    def _count_sentences(body: str) -> int:
        """Count sentence-like units while avoiding a false count for blanks."""

        chunks = [part.strip() for part in _SENTENCE_RE.split(body) if part.strip()]
        return max(1, len(chunks)) if body.strip() else 0


__all__ = ["StatisticsService", "StoryStatistics"]