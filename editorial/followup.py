"""Editorial follow-up recommendations for NewsDesk.

This module converts the key details of a planning application into a short,
prioritised list of practical newsroom follow-up actions.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from editorial.utils import contains_any


HOUSING_TERMS = (
    "dwelling",
    "dwellings",
    "housing",
    "residential",
    "homes",
    "apartment",
    "apartments",
)

ENERGY_STORAGE_TERMS = ("battery", "energy storage", "bess")
RENEWABLE_ENERGY_TERMS = ("solar", "renewable", "photovoltaic", "wind turbine")
COMMERCIAL_TERMS = (
    "commercial",
    "employment",
    "industrial",
    "warehouse",
    "retail",
    "factory",
    "business unit",
)
HERITAGE_TERMS = (
    "listed building",
    "heritage",
    "conservation area",
    "scheduled monument",
)
TELECOMS_TERMS = ("telecom", "mast", "antenna", "5g")
TREE_TERMS = ("tree", "trees", "tpo", "arboricultural")
DEMOLITION_TERMS = ("demolition", "demolish")


CATEGORY_RECOMMENDATIONS: tuple[
    tuple[tuple[str, ...], tuple[str, ...]], ...
] = (
    (
        HOUSING_TERMS,
        (
            "Check the number and type of homes proposed",
            "Review highways, school and health-service implications",
            "Check for public objections or parish council comments",
        ),
    ),
    (
        ENERGY_STORAGE_TERMS,
        (
            "Check fire-safety, access and environmental documents",
            "Identify the site operator and proposed generating capacity",
            "Check parish council and nearby resident responses",
        ),
    ),
    (
        RENEWABLE_ENERGY_TERMS,
        (
            "Review landscape and ecological impact documents",
            "Check the proposed energy output and site lifespan",
            "Look for local objections or community-benefit proposals",
        ),
    ),
    (
        COMMERCIAL_TERMS,
        (
            "Confirm expected jobs and investment",
            "Check traffic, access and operating-hour impacts",
            "Seek comment from the applicant or local business groups",
        ),
    ),
    (
        HERITAGE_TERMS,
        (
            "Review the heritage statement",
            "Check conservation officer comments",
            "Identify any change to a protected building or setting",
        ),
    ),
    (
        TELECOMS_TERMS,
        (
            "Check mast height and exact location",
            "Review coverage justification and visual-impact documents",
            "Check for nearby homes, schools or community facilities",
        ),
    ),
    (
        TREE_TERMS,
        (
            "Check whether protected trees are affected",
            "Review arboricultural reports",
            "Confirm replacement planting or mitigation",
        ),
    ),
    (
        DEMOLITION_TERMS,
        (
            "Identify what is being demolished and why",
            "Check whether redevelopment plans have also been submitted",
        ),
    ),
)

DEFAULT_RECOMMENDATION = (
    "Monitor the application for consultation responses or a decision"
)
MAX_RECOMMENDATIONS = 5


def _application_text(app: Any) -> str:
    """Return searchable text from the application fields used by NewsDesk."""
    values = (
        getattr(app, "proposal", ""),
        getattr(app, "category", ""),
        getattr(app, "address", ""),
    )
    return " ".join(str(value or "") for value in values).lower()


def _application_score(app: Any) -> int:
    """Return the application's score as an integer, defaulting safely to zero."""
    value = getattr(app, "score", 0)

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _score_recommendation(score: int) -> str | None:
    """Return the editorial action associated with the application's score."""
    if score >= 45:
        return "Consider contacting the applicant and council planning team"
    if score >= 35:
        return "Prepare a standalone website story"
    if score >= 25:
        return "Monitor for consultation responses and a decision"
    return None


def _unique_recommendations(recommendations: Iterable[str]) -> list[str]:
    """Deduplicate recommendations while preserving their original order."""
    unique: list[str] = []
    seen: set[str] = set()

    for recommendation in recommendations:
        cleaned = str(recommendation).strip()
        if not cleaned:
            continue

        key = cleaned.casefold()
        if key in seen:
            continue

        seen.add(key)
        unique.append(cleaned)

    return unique


def follow_up_recommendations(app: Any) -> list[str]:
    """Generate up to five concise newsroom follow-up recommendations.

    The public function and returned wording remain compatible with the existing
    editorial engine. Missing or malformed application attributes are handled
    defensively so a partial record cannot break the story workflow.
    """
    text = _application_text(app)
    recommendations: list[str] = []

    for terms, actions in CATEGORY_RECOMMENDATIONS:
        if contains_any(text, terms):
            recommendations.extend(actions)

    score_action = _score_recommendation(_application_score(app))
    if score_action:
        recommendations.append(score_action)

    unique = _unique_recommendations(recommendations)
    if not unique:
        unique.append(DEFAULT_RECOMMENDATION)

    return unique[:MAX_RECOMMENDATIONS]