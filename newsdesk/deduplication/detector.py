"""Detect duplicate stories."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Protocol

from .fingerprint import fingerprint
from .result import DuplicateResult


class ArticleLike(Protocol):
    """Minimum article fields required by the duplicate detector."""

    title: str
    summary: str


@dataclass(slots=True)
class DuplicateDetector:
    """Detect exact and near-duplicate articles."""

    similarity_threshold: float = 0.88
    _seen: dict[str, tuple[str, str]] = field(default_factory=dict)

    def check(self, article: ArticleLike) -> DuplicateResult:
        """Check whether an article has already been seen."""

        title = article.title or ""
        summary = article.summary or ""

        article_fingerprint = fingerprint(title, summary)

        if article_fingerprint in self._seen:
            matched_title, _ = self._seen[article_fingerprint]

            return DuplicateResult(
                duplicate=True,
                confidence=1.0,
                fingerprint=article_fingerprint,
                matched_story=matched_title,
            )

        best_match: str | None = None
        best_score = 0.0

        candidate_text = self._normalise(title, summary)

        for matched_title, matched_summary in self._seen.values():
            existing_text = self._normalise(
                matched_title,
                matched_summary,
            )

            score = SequenceMatcher(
                None,
                candidate_text,
                existing_text,
            ).ratio()

            if score > best_score:
                best_score = score
                best_match = matched_title

        duplicate = best_score >= self.similarity_threshold

        if not duplicate:
            self._seen[article_fingerprint] = (
                title,
                summary,
            )

        return DuplicateResult(
            duplicate=duplicate,
            confidence=best_score if duplicate else 0.0,
            fingerprint=article_fingerprint,
            matched_story=best_match if duplicate else None,
        )

    def add(self, article: ArticleLike) -> str:
        """Register an article without running duplicate checks."""

        article_fingerprint = fingerprint(
            article.title or "",
            article.summary or "",
        )

        self._seen[article_fingerprint] = (
            article.title or "",
            article.summary or "",
        )

        return article_fingerprint

    def add_many(self, articles: Iterable[ArticleLike]) -> None:
        """Register several existing articles."""

        for article in articles:
            self.add(article)

    def clear(self) -> None:
        """Remove all stored article fingerprints."""

        self._seen.clear()

    def __len__(self) -> int:
        """Return the number of stored articles."""

        return len(self._seen)

    @staticmethod
    def _normalise(title: str, summary: str) -> str:
        """Return normalised text for similarity comparison."""

        return " ".join(
            f"{title} {summary}".casefold().split()
        )