"""Editorial decision engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .result import DecisionResult
from .rules import (
    BREAKING_PRIMARY_CATEGORIES,
    EDITOR_REVIEW_CONFIDENCE,
    FACEBOOK_PRIORITY,
    HOMEPAGE_PRIORITY,
    IMMEDIATE_PUBLISH_PRIORITY,
    NEWSLETTER_PRIORITY,
)

if TYPE_CHECKING:
    from ..publishing.builder import BuiltArticle


class DecisionEngine:
    """Convert article classification metadata into publishing decisions."""

    def decide(self, article: BuiltArticle) -> DecisionResult:
        """Return publishing decisions for a built article."""

        classification = article.classification

        if classification is None:
            return DecisionResult(
                publish=True,
                publish_immediately=False,
                homepage=False,
                homepage_rank=5,
                facebook=False,
                newsletter=True,
                breaking_banner=False,
                editor_review=True,
            )

        primary = classification.primary
        priority = classification.priority
        confidence = classification.confidence
        breaking = classification.breaking

        publish_immediately = (
            priority >= IMMEDIATE_PUBLISH_PRIORITY
        )

        homepage = priority >= HOMEPAGE_PRIORITY

        facebook = priority >= FACEBOOK_PRIORITY

        newsletter = priority >= NEWSLETTER_PRIORITY

        breaking_banner = (
            breaking
            or primary in BREAKING_PRIMARY_CATEGORIES
        )

        editor_review = (
            confidence < EDITOR_REVIEW_CONFIDENCE
        )

        homepage_rank = self._homepage_rank(priority)

        return DecisionResult(
            publish=True,
            publish_immediately=publish_immediately,
            homepage=homepage,
            homepage_rank=homepage_rank,
            facebook=facebook,
            newsletter=newsletter,
            breaking_banner=breaking_banner,
            editor_review=editor_review,
        )

    @staticmethod
    def _homepage_rank(priority: int) -> int:
        """Convert classification priority into a homepage rank."""

        if priority >= 90:
            return 1

        if priority >= 75:
            return 2

        if priority >= 60:
            return 3

        if priority >= 50:
            return 4

        return 5