"""
Editorial Gatekeeper

Provides a second editorial pass after priority scoring.

Nothing is deleted.

Each story is classified as:

    visible
    hidden

The original story object is returned with additional metadata stored
in story.extras.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any, Iterable


HIDE_KEYWORDS = (
    "ticket information",
    "season ticket",
    "season tickets",
    "matchday ticket",
    "matchday tickets",
    "hospitality",
    "commercial partnership",
    "commercial partner",
    "sponsorship",
    "sponsor",
    "club shop",
    "merchandise",
    "vacancy",
    "vacancies",
    "job opportunity",
    "job opportunities",
    "recruitment",
    "fixture reminder",
    "fixture list",
    "parking information",
    "mascot package",
    "travel information",
    "supporter information",
    "fan information",
    "membership package",
    "membership packages",
    "corporate package",
    "corporate packages",
)


LOW_VALUE_KEYWORDS = (
    "how to watch",
    "where to watch",
    "watch live",
    "live stream",
    "tv channel",
    "kick-off time",
    "kick off time",
    "confirmed line-up",
    "confirmed lineup",
    "team news",
    "predicted line-up",
    "predicted lineup",
    "starting xi",
    "match preview",
    "matchday guide",
    "programme notes",
    "quiz",
    "vote for",
    "wallpaper",
    "photo gallery",
    "gallery:",
    "training gallery",
    "behind the scenes",
)


RUMOUR_KEYWORDS = (
    "transfer rumour",
    "transfer rumours",
    "rumour",
    "rumours",
    "gossip",
    "linked with",
    "could sign",
    "set to sign",
    "tipped to sign",
    "eyeing move",
    "plotting move",
)


ALWAYS_VISIBLE = (
    "Front Page",
    "High Priority",
)


PRIORITY_RANK = {
    "Front Page": 5,
    "High Priority": 4,
    "Immediate": 4,
    "Urgent": 3,
    "Routine": 2,
    "Low Priority": 1,
}


@dataclass(slots=True)
class EditorialResult:
    visible: bool
    confidence: int
    reason: str


class EditorialGatekeeper:
    """Classify and limit stories shown in the editorial queue."""

    def __init__(
        self,
        max_age_days: int = 14,
        max_visible: int | None = 40,
        minimum_score: int = 30,
        max_per_source: int | None = 15,
    ) -> None:
        self.max_age_days = max_age_days
        self.max_visible = max_visible
        self.minimum_score = minimum_score
        self.max_per_source = max_per_source

    def classify(self, stories: Iterable[Any]):
        """Return visible and hidden stories without deleting any story."""

        candidates: list[Any] = []
        hidden: list[Any] = []

        for story in stories:
            result = self.classify_story(story)
            self._store_result(story, result)

            if result.visible:
                candidates.append(story)
            else:
                hidden.append(story)

        candidates.sort(key=self._sort_key, reverse=True)

        visible: list[Any] = []
        source_counts: dict[str, int] = {}
        seen_fingerprints: set[str] = set()

        for story in candidates:
            fingerprint = self._fingerprint(story)

            if fingerprint and fingerprint in seen_fingerprints:
                result = EditorialResult(
                    False,
                    96,
                    "Duplicate or near-duplicate story",
                )
                self._store_result(story, result)
                hidden.append(story)
                continue

            source_name = self._source_name(story)
            source_count = source_counts.get(source_name, 0)

            if (
                self.max_per_source is not None
                and source_count >= self.max_per_source
                and not self._is_always_visible(story)
            ):
                result = EditorialResult(
                    False,
                    90,
                    f"Source limit reached ({source_name})",
                )
                self._store_result(story, result)
                hidden.append(story)
                continue

            if (
                self.max_visible is not None
                and len(visible) >= self.max_visible
                and not self._is_always_visible(story)
            ):
                result = EditorialResult(
                    False,
                    92,
                    f"Outside top {self.max_visible} editorial stories",
                )
                self._store_result(story, result)
                hidden.append(story)
                continue

            visible.append(story)

            if fingerprint:
                seen_fingerprints.add(fingerprint)

            source_counts[source_name] = source_count + 1

        return visible, hidden

    def classify_story(self, story: Any) -> EditorialResult:
        """Apply first-pass editorial rules to one story."""

        extras = self._extras(story)
        priority = str(extras.get("priority_level", "") or "").strip()

        if priority in ALWAYS_VISIBLE:
            return EditorialResult(
                True,
                100,
                "High editorial priority",
            )

        text = self._story_text(story)

        for keyword in HIDE_KEYWORDS:
            if keyword in text:
                return EditorialResult(
                    False,
                    97,
                    f"Commercial or administrative content ({keyword})",
                )

        for keyword in LOW_VALUE_KEYWORDS:
            if keyword in text:
                return EditorialResult(
                    False,
                    91,
                    f"Low editorial value ({keyword})",
                )

        for keyword in RUMOUR_KEYWORDS:
            if keyword in text:
                return EditorialResult(
                    False,
                    88,
                    f"Transfer speculation ({keyword})",
                )

        published = self._published_date(story)

        if published is not None:
            age = (datetime.now(timezone.utc) - published).days

            if age > self.max_age_days:
                return EditorialResult(
                    False,
                    95,
                    f"Older than {self.max_age_days} days",
                )

        score = self._score(story)

        if score < self.minimum_score:
            return EditorialResult(
                False,
                86,
                f"Editorial score below {self.minimum_score}",
            )

        return EditorialResult(
            True,
            80,
            "Editorially relevant",
        )

    @staticmethod
    def _store_result(story: Any, result: EditorialResult) -> None:
        extras = EditorialGatekeeper._extras(story)
        extras["editorial_visible"] = result.visible
        extras["editorial_confidence"] = result.confidence
        extras["editorial_reason"] = result.reason
        story.extras = extras

    @staticmethod
    def _extras(story: Any) -> dict[str, Any]:
        extras = getattr(story, "extras", None)

        if isinstance(extras, dict):
            return extras

        return {}

    @staticmethod
    def _story_text(story: Any) -> str:
        return " ".join(
            str(getattr(story, field, "") or "")
            for field in (
                "title",
                "summary",
                "description",
                "body",
            )
        ).lower()

    @staticmethod
    def _source_name(story: Any) -> str:
        extras = EditorialGatekeeper._extras(story)

        for value in (
            getattr(story, "source", None),
            getattr(story, "source_name", None),
            extras.get("source"),
            extras.get("source_name"),
        ):
            text = str(value or "").strip()

            if text:
                return text

        return "Unknown source"

    @staticmethod
    def _score(story: Any) -> int:
        extras = EditorialGatekeeper._extras(story)

        for value in (
            extras.get("priority_score"),
            extras.get("score"),
            getattr(story, "priority_score", None),
            getattr(story, "score", None),
        ):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                continue

        priority = str(extras.get("priority_level", "") or "").strip()
        return PRIORITY_RANK.get(priority, 0) * 10

    @staticmethod
    def _sort_key(story: Any):
        extras = EditorialGatekeeper._extras(story)
        priority = str(extras.get("priority_level", "") or "").strip()
        priority_rank = PRIORITY_RANK.get(priority, 0)
        score = EditorialGatekeeper._score(story)
        published = EditorialGatekeeper._published_date(story)

        if published is None:
            published_timestamp = 0.0
        else:
            published_timestamp = published.timestamp()

        return priority_rank, score, published_timestamp

    @staticmethod
    def _fingerprint(story: Any) -> str:
        title = str(getattr(story, "title", "") or "").lower()
        title = re.sub(r"[^a-z0-9\s]", " ", title)

        stop_words = {
            "a",
            "an",
            "and",
            "at",
            "by",
            "for",
            "from",
            "in",
            "is",
            "of",
            "on",
            "the",
            "to",
            "with",
        }

        words = [
            word
            for word in title.split()
            if len(word) > 2 and word not in stop_words
        ]

        return " ".join(words[:10])

    @staticmethod
    def _is_always_visible(story: Any) -> bool:
        extras = EditorialGatekeeper._extras(story)
        priority = str(extras.get("priority_level", "") or "").strip()
        return priority in ALWAYS_VISIBLE

    @staticmethod
    def _published_date(story: Any):
        for field in (
            "published",
            "published_date",
            "published_at",
            "date",
        ):
            value = getattr(story, field, None)

            if not value:
                continue

            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.replace(tzinfo=timezone.utc)

                return value.astimezone(timezone.utc)

            text = str(value).strip()

            if not text:
                continue

            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                return dt.astimezone(timezone.utc)

            except (TypeError, ValueError):
                pass

            try:
                dt = parsedate_to_datetime(text)

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                return dt.astimezone(timezone.utc)

            except (TypeError, ValueError, OverflowError):
                pass

        return None


__all__ = [
    "EditorialGatekeeper",
    "EditorialResult",
]
