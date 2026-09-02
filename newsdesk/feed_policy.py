"""Shared location-and-date policy for Devour intelligence feeds."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

from newsdesk.geography.lincolnshire import story_matches_lincolnshire


def published_datetime(value: object) -> datetime | None:
    """Parse the common publication-date formats used by source adapters."""

    text = str(value or "").strip()
    if not text:
        return None

    candidates = (text, text.replace("Z", "+00:00"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def newest_first(stories: Iterable[object]) -> list[object]:
    """Return stories in descending publication order, deterministically."""

    def key(story: object) -> tuple[float, str]:
        parsed = published_datetime(getattr(story, "published", ""))
        timestamp = parsed.timestamp() if parsed is not None else float("-inf")
        return timestamp, str(getattr(story, "title", "") or "").casefold()

    return sorted(stories, key=key, reverse=True)


def lincolnshire_only(stories: Iterable[object]) -> list[object]:
    """Keep stories with explainable Lincolnshire evidence and record it."""

    retained: list[object] = []
    for story in stories:
        match = story_matches_lincolnshire(story)
        if not match.matched:
            continue
        extras = getattr(story, "extras", None)
        if isinstance(extras, dict):
            extras["geographic_filter"] = "lincolnshire"
            extras["geographic_matches"] = list(match.places)
        retained.append(story)
    return retained


def prepare_lincolnshire_feed(stories: Iterable[object]) -> list[object]:
    """Apply Devour's complete editorial policy: Lincolnshire, newest first."""

    return newest_first(lincolnshire_only(stories))


__all__ = [
    "lincolnshire_only",
    "newest_first",
    "prepare_lincolnshire_feed",
    "published_datetime",
]
