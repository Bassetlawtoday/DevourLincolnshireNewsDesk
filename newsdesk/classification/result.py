"""Story classification result models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ClassificationResult:
    """Represents the editorial classification of a story."""

    primary: str
    confidence: float

    secondary: list[str] = field(
        default_factory=list
    )

    matched_keywords: dict[str, int] = field(
        default_factory=dict
    )

    scores: dict[str, int] = field(
        default_factory=dict
    )

    priority: int = 50
    breaking: bool = False
    location_type: str = "unknown"