"""Editorial scoring helpers used by the planning and editorial modules.

This module intentionally preserves the original public API and score bands:

``editorial_priority(score)``
    Return the newsroom treatment label for one score.

``priority_stars(score)``
    Return the corresponding one-to-five star rating.

``editorial_summary(applications)``
    Count a collection of scored records by treatment label.

The helpers are deliberately small and dependency-free because they are used by
both the current NewsDesk services and older planning workflows.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class _ScoreBand:
    """One editorial score threshold and its associated output values."""

    minimum_score: int
    label: str
    stars: int
    summary_key: str


_SCORE_BANDS: Final[tuple[_ScoreBand, ...]] = (
    _ScoreBand(45, "FRONT PAGE", 5, "front_page"),
    _ScoreBand(35, "LEAD WEBSITE STORY", 4, "lead_website"),
    _ScoreBand(25, "WEBSITE STORY", 3, "website_story"),
    _ScoreBand(15, "BRIEF MENTION", 2, "brief_mention"),
    _ScoreBand(0, "ARCHIVE", 1, "archive"),
)

_SUMMARY_KEYS: Final[tuple[str, ...]] = tuple(
    band.summary_key for band in _SCORE_BANDS
)
_LABEL_TO_SUMMARY_KEY: Final[dict[str, str]] = {
    band.label: band.summary_key for band in _SCORE_BANDS
}


def _coerce_score(value: object) -> int:
    """Convert a score-like value to ``int`` without raising.

    The previous implementation treated falsey values as zero and accepted any
    value supported by ``int``. This helper keeps that behaviour while making
    invalid external data safe for the UI and summary pipeline.
    """

    if value is None or value == "":
        return 0

    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _band_for_score(score: object) -> _ScoreBand:
    """Return the configured score band for ``score``."""

    numeric_score = _coerce_score(score)

    for band in _SCORE_BANDS:
        if numeric_score >= band.minimum_score:
            return band

    # The final band starts at zero, but negative scores must still archive.
    return _SCORE_BANDS[-1]


def editorial_priority(score: object) -> str:
    """Return the recommended editorial treatment for a score.

    The established thresholds are preserved exactly:

    * 45 or more: ``FRONT PAGE``
    * 35–44: ``LEAD WEBSITE STORY``
    * 25–34: ``WEBSITE STORY``
    * 15–24: ``BRIEF MENTION``
    * below 15: ``ARCHIVE``
    """

    return _band_for_score(score).label


def priority_stars(score: object) -> int:
    """Return the established one-to-five-star editorial priority rating."""

    return _band_for_score(score).stars


def _record_score(record: object) -> object:
    """Read ``score`` from an object or mapping.

    Planning records are normally dataclass instances, but accepting mappings
    makes the helper safe for exported/imported data and lightweight tests.
    """

    if isinstance(record, Mapping):
        return record.get("score", 0)

    return getattr(record, "score", 0)


def editorial_summary(applications: Iterable[Any] | None) -> dict[str, int]:
    """Count applications by editorial recommendation.

    ``None`` is treated as an empty collection. Individual malformed records do
    not interrupt the summary; their score is treated as zero and therefore
    counted under ``archive``.
    """

    counts: Counter[str] = Counter()

    for application in applications or ():
        label = editorial_priority(_record_score(application))
        counts[_LABEL_TO_SUMMARY_KEY[label]] += 1

    return {key: counts.get(key, 0) for key in _SUMMARY_KEYS}


__all__ = [
    "editorial_priority",
    "priority_stars",
    "editorial_summary",
]