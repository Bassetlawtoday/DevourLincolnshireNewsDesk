"""Duplicate detection result."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DuplicateResult:
    """Result returned by the duplicate detector."""

    duplicate: bool = False

    confidence: float = 0.0

    fingerprint: str = ""

    matched_story: str | None = None