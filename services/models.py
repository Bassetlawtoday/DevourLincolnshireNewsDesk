from dataclasses import dataclass, field
from typing import List


@dataclass
class PlanningApplication:

    reference: str = ""
    alt_reference: str = ""

    address: str = ""
    proposal: str = ""

    status: str = ""
    decision: str = ""

    received_date: str = ""
    validated_date: str = ""
    decision_date: str = ""

    appeal_status: str = ""
    appeal_decision: str = ""

    category: str = ""

    # Exact public-register detail page captured from the weekly results.
    url: str = ""

    score: int = 0

    tags: List[str] = field(default_factory=list)

    notes: str = ""


@dataclass
class PoliceArticle:
    """Raw police press-release data collected by the Police module."""

    headline: str = ""
    summary: str = ""
    body: str = ""

    location: str = ""
    published_date: str = ""

    source: str = "Nottinghamshire Police"
    source_url: str = ""

    reference: str = ""
    status: str = ""

    quotes: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)

    category: str = ""
    notes: str = ""


@dataclass
class NewsStory:
    """Common newsroom story model used by every NewsDesk module."""

    source_type: str = ""

    headline: str = ""
    summary: str = ""
    body: str = ""

    location: str = ""
    area: str = ""

    published_date: str = ""
    source: str = ""
    source_url: str = ""

    score: int = 0
    rating: int = 1

    category: str = ""
    editorial_angle: str = ""

    matched_place: str = ""
    priority_level: str = ""
    editorial_zone: str = ""

    tags: List[str] = field(default_factory=list)
    why_news: List[str] = field(default_factory=list)
    follow_up: List[str] = field(default_factory=list)

    priority_reasons: List[str] = field(default_factory=list)
    matched_signals: List[str] = field(default_factory=list)

    # Structured editorial classification
    primary_category: str = ""
    secondary_category: str = ""
    crime_type: str = ""
    severity: str = ""
    victim_type: str = ""
    story_type: str = ""
    public_interest: str = ""
    developing: bool = False
    classification_signals: List[str] = field(default_factory=list)
