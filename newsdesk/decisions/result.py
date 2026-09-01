"""Decision result produced by the editorial decision engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DecisionResult:
    """Editorial publishing decisions for an article."""

    publish: bool = True

    publish_immediately: bool = False

    homepage: bool = True

    homepage_rank: int = 5

    facebook: bool = True

    newsletter: bool = True

    breaking_banner: bool = False

    editor_review: bool = False