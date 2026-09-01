"""Central editorial analysis engine for NewsDesk.

This module provides the legacy editorial-analysis entry points used by the
planning and police workflows.  The public functions are intentionally kept
stable so existing imports continue to work while the shared analysis-building
logic is maintained in one place.
"""

from __future__ import annotations

from typing import Any

from editorial.followup import follow_up_recommendations
from editorial.scoring import editorial_priority, priority_stars
from editorial.story_analysis import why_is_it_news
from editorial.story_tags import story_tags


def _normalise_score(story: Any) -> int:
    """Return a safe integer score for an editorial story object."""

    value = getattr(story, "score", 0)

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_analysis(story: Any) -> dict[str, Any]:
    """Build the standard editorial-analysis payload for one story."""

    score = _normalise_score(story)

    return {
        "editorial_priority": editorial_priority(score),
        "priority_stars": priority_stars(score),
        "why_news": why_is_it_news(story),
        "tags": story_tags(story),
        "follow_up": follow_up_recommendations(story),
    }


def analyse_application(app: Any) -> dict[str, Any]:
    """Return the complete editorial analysis for a planning application."""

    return _build_analysis(app)


def analyse_police_article(article: Any) -> dict[str, Any]:
    """Return the complete editorial analysis for a police article."""

    return _build_analysis(article)


def analyse_story(story: Any) -> dict[str, Any]:
    """Analyse any story type supported by the legacy editorial engine."""

    if hasattr(story, "application_number"):
        return analyse_application(story)

    if hasattr(story, "crime_type") or hasattr(story, "quotes"):
        return analyse_police_article(story)

    raise TypeError(
        f"Unsupported story type: {type(story).__name__}"
    )


__all__ = [
    "analyse_application",
    "analyse_police_article",
    "analyse_story",
]