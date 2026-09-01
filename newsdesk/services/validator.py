"""
newsdesk.services.validator

Validation services for NewsDesk stories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from newsdesk.story import Story


@dataclass(slots=True)
class ValidationResult:
    """Result returned after validating a story."""

    valid: bool
    errors: list[str] = field(default_factory=list)


class StoryValidator:
    """Validate ``Story`` objects before they enter publishing workflows."""

    MIN_TITLE_LENGTH: Final[int] = 8
    MIN_BODY_LENGTH: Final[int] = 50

    def validate(self, story: Story) -> ValidationResult:
        """Return all title and body validation errors for ``story``."""

        if not isinstance(story, Story):
            return ValidationResult(
                valid=False,
                errors=["Invalid story object."],
            )

        errors: list[str] = []
        title = self._normalise_text(story.title)
        body = self._normalise_text(story.body)

        self._validate_title(title, errors)
        self._validate_body(body, errors)

        return ValidationResult(
            valid=not errors,
            errors=errors,
        )

    def _validate_title(
        self,
        title: str,
        errors: list[str],
    ) -> None:
        if not title:
            errors.append("Missing title.")
        elif len(title) < self.MIN_TITLE_LENGTH:
            errors.append("Title is too short.")

    def _validate_body(
        self,
        body: str,
        errors: list[str],
    ) -> None:
        if not body:
            errors.append("Missing body.")
        elif len(body) < self.MIN_BODY_LENGTH:
            errors.append("Body is too short.")

    @staticmethod
    def _normalise_text(value: object) -> str:
        """Return stripped text without allowing malformed values to crash."""

        if value is None:
            return ""

        return str(value).strip()


__all__ = [
    "StoryValidator",
    "ValidationResult",
]