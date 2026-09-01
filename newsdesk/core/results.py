"""
newsdesk.core.results

Shared collection-result models for Devour Lincolnshire NewsDesk.

These models provide a common result format for every NewsDesk module,
including Police, Planning, Fire, Council, Business, Sport and the future
National, International and Social Media Intelligence services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar


ItemType = TypeVar("ItemType")


def utc_now() -> datetime:
    """
    Return the current timezone-aware UTC datetime.
    """

    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CollectionError:
    """
    Structured information about a collection or processing failure.

    A collection run may contain errors without failing completely. This is
    important for multi-source services where one unavailable source should
    not prevent the remaining sources from being collected.
    """

    message: str
    source: str = ""
    stage: str = ""
    exception_type: str = ""
    recoverable: bool = True
    occurred_at: datetime = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exception(
        cls,
        error: BaseException,
        *,
        source: str = "",
        stage: str = "",
        recoverable: bool = True,
        details: dict[str, Any] | None = None,
    ) -> "CollectionError":
        """
        Create a CollectionError from an exception.
        """

        return cls(
            message=str(error) or error.__class__.__name__,
            source=source,
            stage=stage,
            exception_type=error.__class__.__name__,
            recoverable=recoverable,
            details=dict(details or {}),
        )

    def __str__(self) -> str:
        """
        Return a useful human-readable error description.
        """

        context = " / ".join(
            value
            for value in (self.source, self.stage)
            if value
        )

        if context:
            return f"{context}: {self.message}"

        return self.message


@dataclass(slots=True)
class CollectionStatistics:
    """
    Shared statistics for one collection run.

    Module-specific statistics can be stored in extras without changing the
    shared framework.
    """

    sources_requested: int = 0
    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0

    items_found: int = 0
    items_collected: int = 0
    items_duplicate: int = 0
    items_rejected: int = 0
    items_processed: int = 0
    items_newsworthy: int = 0

    publish_attempted: int = 0
    publish_succeeded: int = 0
    publish_failed: int = 0

    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def source_success_rate(self) -> float:
        """
        Return the percentage of attempted sources that succeeded.
        """

        if self.sources_attempted <= 0:
            return 0.0

        return round(
            (self.sources_succeeded / self.sources_attempted) * 100,
            2,
        )

    @property
    def publish_success_rate(self) -> float:
        """
        Return the percentage of attempted publications that succeeded.
        """

        if self.publish_attempted <= 0:
            return 0.0

        return round(
            (self.publish_succeeded / self.publish_attempted) * 100,
            2,
        )

    def set_extra(
        self,
        name: str,
        value: Any,
    ) -> None:
        """
        Store a module-specific statistic.
        """

        cleaned_name = str(name).strip()

        if not cleaned_name:
            raise ValueError(
                "Collection statistic names cannot be empty."
            )

        self.extras[cleaned_name] = value

    def get_extra(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Return a module-specific statistic.
        """

        return self.extras.get(name, default)

    def as_dict(self) -> dict[str, Any]:
        """
        Return statistics in a serialisable dictionary.
        """

        return {
            "sources_requested": self.sources_requested,
            "sources_attempted": self.sources_attempted,
            "sources_succeeded": self.sources_succeeded,
            "sources_failed": self.sources_failed,
            "items_found": self.items_found,
            "items_collected": self.items_collected,
            "items_duplicate": self.items_duplicate,
            "items_rejected": self.items_rejected,
            "items_processed": self.items_processed,
            "items_newsworthy": self.items_newsworthy,
            "publish_attempted": self.publish_attempted,
            "publish_succeeded": self.publish_succeeded,
            "publish_failed": self.publish_failed,
            "source_success_rate": self.source_success_rate,
            "publish_success_rate": self.publish_success_rate,
            "extras": dict(self.extras),
        }


@dataclass(slots=True)
class PublishSummary:
    """
    Shared publication summary for a collection run.
    """

    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[Any] = field(default_factory=list)
    errors: list[CollectionError] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        """
        Return True when publication completed without failures.
        """

        return self.failed == 0 and not self.errors

    @property
    def success_rate(self) -> float:
        """
        Return the percentage of attempted publications that succeeded.
        """

        if self.attempted <= 0:
            return 0.0

        return round(
            (self.succeeded / self.attempted) * 100,
            2,
        )


@dataclass(slots=True)
class CollectionResult(Generic[ItemType]):
    """
    Generic result returned by every NewsDesk collection service.

    The items collection may contain Story objects, PlanningApplication
    objects or another module-specific model. The shared dashboard only needs
    the common metadata, statistics and error information.
    """

    module: str
    items: list[ItemType] = field(default_factory=list)
    newsworthy_items: list[ItemType] = field(default_factory=list)

    statistics: CollectionStatistics = field(
        default_factory=CollectionStatistics
    )
    publish_summary: PublishSummary = field(
        default_factory=PublishSummary
    )
    errors: list[CollectionError] = field(default_factory=list)

    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def successful(self) -> bool:
        """
        Return True when the collection run has no fatal errors.

        Recoverable source errors are retained for reporting but do not mark
        the entire run as failed.
        """

        return not any(
            not error.recoverable
            for error in self.errors
        )

    @property
    def has_errors(self) -> bool:
        """
        Return True when any errors were recorded.
        """

        return bool(self.errors)

    @property
    def partial_success(self) -> bool:
        """
        Return True when useful items were collected despite errors.
        """

        return bool(self.items) and self.has_errors

    @property
    def finished(self) -> bool:
        """
        Return True when the collection run has been completed.
        """

        return self.completed_at is not None

    @property
    def duration_seconds(self) -> float:
        """
        Return the collection duration in seconds.
        """

        endpoint = self.completed_at or utc_now()

        return max(
            0.0,
            (endpoint - self.started_at).total_seconds(),
        )

    @property
    def item_count(self) -> int:
        """
        Return the total number of collected items.
        """

        return len(self.items)

    @property
    def newsworthy_count(self) -> int:
        """
        Return the number of newsworthy items.
        """

        return len(self.newsworthy_items)

    def add_error(
        self,
        error: CollectionError | BaseException | str,
        *,
        source: str = "",
        stage: str = "",
        recoverable: bool = True,
        details: dict[str, Any] | None = None,
    ) -> CollectionError:
        """
        Add an error to the collection result.

        Exceptions and plain strings are converted into CollectionError
        instances automatically.
        """

        if isinstance(error, CollectionError):
            collection_error = error

        elif isinstance(error, BaseException):
            collection_error = CollectionError.from_exception(
                error,
                source=source,
                stage=stage,
                recoverable=recoverable,
                details=details,
            )

        else:
            collection_error = CollectionError(
                message=str(error),
                source=source,
                stage=stage,
                recoverable=recoverable,
                details=dict(details or {}),
            )

        self.errors.append(collection_error)

        return collection_error

    def finish(self) -> "CollectionResult[ItemType]":
        """
        Mark the collection run as complete and synchronise key statistics.
        """

        if self.completed_at is None:
            self.completed_at = utc_now()

        self.statistics.items_collected = len(self.items)
        self.statistics.items_newsworthy = len(
            self.newsworthy_items
        )

        self.statistics.publish_attempted = (
            self.publish_summary.attempted
        )
        self.statistics.publish_succeeded = (
            self.publish_summary.succeeded
        )
        self.statistics.publish_failed = (
            self.publish_summary.failed
        )

        return self

    def set_metadata(
        self,
        name: str,
        value: Any,
    ) -> None:
        """
        Store collection metadata for dashboards or specialist modules.
        """

        cleaned_name = str(name).strip()

        if not cleaned_name:
            raise ValueError(
                "Collection metadata names cannot be empty."
            )

        self.metadata[cleaned_name] = value

    def summary(self) -> dict[str, Any]:
        """
        Return a serialisable high-level collection summary.

        This structure is suitable for the future unified newsroom dashboard.
        """

        return {
            "module": self.module,
            "successful": self.successful,
            "partial_success": self.partial_success,
            "finished": self.finished,
            "item_count": self.item_count,
            "newsworthy_count": self.newsworthy_count,
            "error_count": len(self.errors),
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at
                else None
            ),
            "duration_seconds": round(
                self.duration_seconds,
                3,
            ),
            "statistics": self.statistics.as_dict(),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "CollectionError",
    "CollectionResult",
    "CollectionStatistics",
    "PublishSummary",
    "utc_now",
]
