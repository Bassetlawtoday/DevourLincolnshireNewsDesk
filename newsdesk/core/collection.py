"""
Shared collection result models.

CollectionResult is the standard outcome returned by every NewsDesk
collection service. It records timing, processing totals, warnings,
errors, cancellation state and optional service-specific metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CollectionResult:
    """
    Represents the outcome of a NewsDesk collection task.

    The existing public fields remain intentionally simple so collection
    services can update the result while they work.

    Attributes:
        source:
            Human-readable name of the source or collection service.

        started:
            Date and time at which collection began.

        finished:
            Date and time at which collection finished. While collection
            is running, this may temporarily contain the start time.

        items_found:
            Total number of source items discovered.

        items_processed:
            Total number of discovered items successfully processed.

        errors:
            Fatal or significant problems encountered during collection.

        metadata:
            Optional service-specific diagnostic or summary information.

        warnings:
            Non-fatal issues that did not prevent collection completing.

        cancelled:
            True when collection was deliberately stopped before completion.
    """

    source: str
    started: datetime
    finished: datetime

    items_found: int = 0
    items_processed: int = 0

    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    cancelled: bool = False

    @property
    def duration_seconds(self) -> float:
        """
        Return the collection duration in seconds.
        """

        return max(
            0.0,
            (self.finished - self.started).total_seconds(),
        )

    @property
    def successful(self) -> bool:
        """
        Return True when collection completed without errors or cancellation.
        """

        return not self.errors and not self.cancelled

    @property
    def completed(self) -> bool:
        """
        Return True when collection was not cancelled.
        """

        return not self.cancelled

    @property
    def has_errors(self) -> bool:
        """
        Return True when one or more errors were recorded.
        """

        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        """
        Return True when one or more warnings were recorded.
        """

        return bool(self.warnings)

    @property
    def items_skipped(self) -> int:
        """
        Return the number of discovered items that were not processed.

        A defensive maximum prevents negative values if a service reports
        processed items before updating its discovered-item total.
        """

        return max(
            0,
            self.items_found - self.items_processed,
        )

    def add_error(self, error: object) -> None:
        """
        Record an error using a safe human-readable representation.
        """

        message = str(error).strip()

        if message:
            self.errors.append(message)

    def add_warning(self, warning: object) -> None:
        """
        Record a non-fatal warning.
        """

        message = str(warning).strip()

        if message:
            self.warnings.append(message)

    def set_metadata(self, key: str, value: Any) -> None:
        """
        Store service-specific metadata.

        Raises:
            ValueError:
                If the metadata key is empty.
        """

        clean_key = key.strip()

        if not clean_key:
            raise ValueError("Metadata key cannot be empty.")

        self.metadata[clean_key] = value

    def mark_cancelled(self) -> None:
        """
        Mark the collection task as cancelled.
        """

        self.cancelled = True

    def mark_finished(
        self,
        finished: datetime | None = None,
    ) -> None:
        """
        Record the collection completion time.

        When no value is supplied, the current local time is used.
        """

        self.finished = finished or datetime.now()

    def summary(self) -> str:
        """
        Return a concise human-readable collection summary.
        """

        if self.cancelled:
            outcome = "cancelled"
        elif self.errors:
            outcome = "completed with errors"
        elif self.warnings:
            outcome = "completed with warnings"
        else:
            outcome = "completed successfully"

        return (
            f"{self.source} {outcome}: "
            f"{self.items_processed} of {self.items_found} items processed "
            f"in {self.duration_seconds:.2f} seconds"
        )