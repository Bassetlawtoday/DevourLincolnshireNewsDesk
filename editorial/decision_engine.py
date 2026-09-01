"""Editorial publishing recommendations for NewsDesk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from services.models import NewsStory


@dataclass
class EditorialDecision:
    """Recommended newsroom actions for a NewsStory."""

    urgency: str = "Routine"

    publish_now: bool = False
    publish_website: bool = False
    publish_facebook: bool = False
    include_newsletter: bool = False
    breaking_banner: bool = False

    needs_editor_review: bool = False
    follow_up_required: bool = False
    archive_only: bool = False

    recommended_channels: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a serialisable version of the decision."""

        return {
            "urgency": self.urgency,
            "publish_now": self.publish_now,
            "publish_website": self.publish_website,
            "publish_facebook": self.publish_facebook,
            "include_newsletter": self.include_newsletter,
            "breaking_banner": self.breaking_banner,
            "needs_editor_review": self.needs_editor_review,
            "follow_up_required": self.follow_up_required,
            "archive_only": self.archive_only,
            "recommended_channels": list(self.recommended_channels),
            "decision_reasons": list(self.reasons),
            "recommended_actions": list(self.actions),
        }


def _normalise(value: object) -> str:
    """Return a compact, case-insensitive string."""

    return " ".join(str(value or "").casefold().split())


def _story_score(story: NewsStory) -> int:
    """Return the story score safely."""

    try:
        return int(getattr(story, "score", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _story_rating(story: NewsStory) -> int:
    """Return the one-to-five priority rating safely."""

    try:
        return max(1, min(5, int(getattr(story, "rating", 1) or 1)))
    except (TypeError, ValueError):
        return 1


def _story_text(story: NewsStory) -> str:
    """Return searchable story and classification text."""

    values: Iterable[object] = (
        getattr(story, "headline", ""),
        getattr(story, "summary", ""),
        getattr(story, "body", ""),
        getattr(story, "category", ""),
        getattr(story, "primary_category", ""),
        getattr(story, "secondary_category", ""),
        getattr(story, "crime_type", ""),
        getattr(story, "severity", ""),
        getattr(story, "story_type", ""),
        *(getattr(story, "matched_signals", None) or ()),
        *(getattr(story, "classification_signals", None) or ()),
    )
    return _normalise(" ".join(str(value or "") for value in values))


def _add_unique(values: list[str], value: str) -> None:
    """Append a non-empty value once."""

    if value and value not in values:
        values.append(value)


def _priority_level(story: NewsStory) -> str:
    return _normalise(getattr(story, "priority_level", ""))


def _is_high_priority(story: NewsStory) -> bool:
    level = _priority_level(story)
    return (
        level in {"front page", "high priority", "top story", "breaking"}
        or _story_rating(story) >= 4
        or _story_score(story) >= 60
    )


def _is_newsworthy(story: NewsStory) -> bool:
    level = _priority_level(story)
    return (
        _is_high_priority(story)
        or level in {"newsworthy", "website story"}
        or _story_rating(story) >= 3
        or _story_score(story) >= 35
    )


def _determine_urgency(story: NewsStory) -> str:
    """Determine how quickly the newsroom should act."""

    severity = _normalise(getattr(story, "severity", ""))
    story_type = _normalise(getattr(story, "story_type", ""))
    public_interest = _normalise(getattr(story, "public_interest", ""))
    level = _priority_level(story)
    rating = _story_rating(story)

    if story_type == "breaking" or severity == "critical":
        return "Immediate"

    if level == "front page" or rating >= 5:
        return "Immediate"

    if bool(getattr(story, "developing", False)):
        return "Urgent"

    if severity == "high" or public_interest == "very high":
        return "Urgent"

    if level in {"high priority", "top story", "breaking"} or rating == 4:
        return "Urgent"

    if severity == "medium" or _is_newsworthy(story):
        return "Normal"

    return "Routine"


def _should_publish_website(story: NewsStory) -> bool:
    severity = _normalise(getattr(story, "severity", ""))
    public_interest = _normalise(getattr(story, "public_interest", ""))

    if severity in {"critical", "high", "medium"}:
        return True

    if public_interest in {"very high", "high", "medium"}:
        return True

    return _is_newsworthy(story)


def _should_publish_facebook(story: NewsStory) -> bool:
    secondary_category = _normalise(
        getattr(story, "secondary_category", "")
    )
    public_interest = _normalise(getattr(story, "public_interest", ""))
    severity = _normalise(getattr(story, "severity", ""))
    score = _story_score(story)

    if secondary_category in {"public appeal", "warning", "community"}:
        return True

    if severity in {"critical", "high"}:
        return True

    if public_interest in {"very high", "high"}:
        return True

    return _is_high_priority(story) or score >= 40


def _should_include_newsletter(story: NewsStory) -> bool:
    severity = _normalise(getattr(story, "severity", ""))
    public_interest = _normalise(getattr(story, "public_interest", ""))
    level = _priority_level(story)

    if severity in {"critical", "high", "medium"}:
        return True

    if public_interest in {"very high", "high", "medium"}:
        return True

    if level == "monitor" or _story_rating(story) >= 2:
        return True

    return _story_score(story) >= 20


def _requires_editor_review(story: NewsStory) -> bool:
    """Return whether an editor should check the story before publication."""

    primary_category = _normalise(getattr(story, "primary_category", ""))
    secondary_category = _normalise(
        getattr(story, "secondary_category", "")
    )
    severity = _normalise(getattr(story, "severity", ""))
    victim_type = _normalise(getattr(story, "victim_type", ""))
    text = _story_text(story)

    sensitive_categories = {
        "homicide",
        "fatal collision",
        "fatal fire",
        "sexual offence",
        "domestic abuse",
        "missing person",
    }
    sensitive_victims = {"child", "teenager", "elderly"}
    legal_stages = {"court", "sentencing", "investigation"}
    sensitive_fire_signals = {
        "fatality",
        "fatal fire",
        "persons reported",
        "serious injury",
        "explosion",
        "hazardous materials",
        "chemical incident",
    }

    if primary_category in sensitive_categories:
        return True

    if victim_type in sensitive_victims:
        return True

    if severity == "critical":
        return True

    if secondary_category in legal_stages:
        return True

    return any(signal in text for signal in sensitive_fire_signals)


def _requires_follow_up(story: NewsStory) -> bool:
    """Return whether the story should remain on the newsroom watchlist."""

    secondary_category = _normalise(
        getattr(story, "secondary_category", "")
    )
    primary_category = _normalise(getattr(story, "primary_category", ""))
    text = _story_text(story)

    if bool(getattr(story, "developing", False)):
        return True

    if secondary_category in {"public appeal", "investigation"}:
        return True

    if primary_category == "missing person":
        return True

    if any(
        signal in text
        for signal in (
            "major incident",
            "road closed",
            "road closure",
            "persons reported",
            "evacuation",
            "wildfire",
        )
    ):
        return True

    return bool(getattr(story, "follow_up", None))


def make_editorial_decision(story: NewsStory) -> EditorialDecision:
    """Produce recommended editorial actions for a NewsStory.

    The public API and returned fields are unchanged. Decisions now understand
    the shared priority engine's levels and ratings, so Police and Fire stories
    receive consistent channel recommendations.
    """

    urgency = _determine_urgency(story)
    publish_website = _should_publish_website(story)
    publish_facebook = _should_publish_facebook(story)
    include_newsletter = _should_include_newsletter(story)
    needs_editor_review = _requires_editor_review(story)
    follow_up_required = _requires_follow_up(story)

    severity = _normalise(getattr(story, "severity", ""))
    story_type = _normalise(getattr(story, "story_type", ""))
    public_interest = _normalise(getattr(story, "public_interest", ""))
    level = _priority_level(story)
    rating = _story_rating(story)

    breaking_banner = (
        (story_type == "breaking" and severity == "critical")
        or level == "front page"
        or rating >= 5
    )

    archive_only = not any(
        (publish_website, publish_facebook, include_newsletter)
    )
    publish_now = urgency in {"Immediate", "Urgent"} and not archive_only

    channels: list[str] = []
    reasons: list[str] = []
    actions: list[str] = []

    if publish_website:
        _add_unique(channels, "Website")
    if publish_facebook:
        _add_unique(channels, "Facebook")
    if include_newsletter:
        _add_unique(channels, "Newsletter")
    if breaking_banner:
        _add_unique(channels, "Breaking Banner")

    if severity == "critical":
        reasons.append("The classifier marked the story as critical.")
    elif severity == "high":
        reasons.append("The classifier marked the story as high severity.")

    if public_interest == "very high":
        reasons.append("The story has very high public interest.")
    elif public_interest == "high":
        reasons.append("The story has high public interest.")

    if bool(getattr(story, "developing", False)):
        reasons.append("The story is developing and may change.")

    matched_place = str(getattr(story, "matched_place", "") or "").strip()
    if matched_place:
        reasons.append(f"The story directly affects {matched_place}.")

    priority_level = str(
        getattr(story, "priority_level", "") or ""
    ).strip()
    if priority_level:
        reasons.append(
            f"The priority engine rated it {priority_level} "
            f"({_story_score(story)} points, {rating}/5)."
        )

    for priority_reason in getattr(story, "priority_reasons", None) or ():
        _add_unique(reasons, str(priority_reason))

    if publish_now:
        actions.append("Prepare the story for prompt publication.")
    elif publish_website:
        actions.append("Add the story to the normal website publishing queue.")

    if publish_facebook:
        actions.append("Prepare a Facebook version of the story.")
    if include_newsletter:
        actions.append("Save the story for the next newsletter.")
    if needs_editor_review:
        actions.append("Complete an editorial and legal review before publication.")
    if follow_up_required:
        actions.append("Keep the story on the follow-up watchlist.")
    if breaking_banner:
        actions.append("Consider displaying a breaking-news banner.")

    if archive_only:
        reasons.append("The story does not currently meet the publishing thresholds.")
        actions.append("Archive the story unless an editor decides otherwise.")

    if not reasons:
        reasons.append(
            "The recommendation is based on the story score and classification."
        )

    return EditorialDecision(
        urgency=urgency,
        publish_now=publish_now,
        publish_website=publish_website,
        publish_facebook=publish_facebook,
        include_newsletter=include_newsletter,
        breaking_banner=breaking_banner,
        needs_editor_review=needs_editor_review,
        follow_up_required=follow_up_required,
        archive_only=archive_only,
        recommended_channels=channels,
        reasons=reasons,
        actions=actions,
    )