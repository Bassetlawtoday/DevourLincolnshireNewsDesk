"""
Base class for all NewsDesk collection services.

The base service owns the standard collection lifecycle::

    create result
        ↓
    before_collect()
        ↓
    _collect()
        ↓
    after_collect()
        ↓
    finalise result

Derived services normally only need to implement :meth:`_collect`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Final

from newsdesk.core.collection import CollectionResult


class BaseCollectionService(ABC):
    """
    Base class for every NewsDesk collection service.

    The class provides a consistent lifecycle, timing, exception handling
    and result reporting while allowing derived services to implement their
    own source-specific collection logic.

    Lifecycle hooks:

    ``before_collect(result)``
        Optional preparation before collection begins.

    ``_collect(result)``
        Required source-specific collection implementation.

    ``after_collect(result)``
        Optional cleanup or final result processing.

    Exceptions raised during any lifecycle stage are recorded in the
    :class:`~newsdesk.core.collection.CollectionResult` rather than escaping
    from :meth:`collect`.
    """

    source_name: str = "Unknown"

    _UNKNOWN_SOURCE: Final[str] = "Unknown"

    def collect(self) -> CollectionResult:
        """
        Run the complete collection lifecycle.

        Returns:
            CollectionResult:
                The final result, including timing, totals, warnings,
                errors, cancellation state and service metadata.
        """

        result = self._create_result()

        try:
            self.before_collect(result)

            if not result.cancelled:
                self._collect(result)

        except Exception as error:
            result.add_error(error)

        finally:
            self._run_after_collect(result)
            result.mark_finished()

        return result

    def _create_result(self) -> CollectionResult:
        """Create the result object used throughout one collection run."""

        started = datetime.now()

        return CollectionResult(
            source=self._normalised_source_name(),
            started=started,
            finished=started,
        )

    def _normalised_source_name(self) -> str:
        """Return a safe, non-empty source name for result reporting."""

        value = str(self.source_name or "").strip()
        return value or self._UNKNOWN_SOURCE

    def _run_after_collect(self, result: CollectionResult) -> None:
        """Run finalisation without allowing cleanup errors to escape."""

        try:
            self.after_collect(result)
        except Exception as error:
            result.add_error(f"Collection cleanup failed: {error}")

    def before_collect(self, result: CollectionResult) -> None:
        """
        Prepare for collection.

        Derived services may override this hook to initialise temporary
        state, validate configuration, open resources or add metadata.

        The default implementation performs no action.
        """

        del result

    @abstractmethod
    def _collect(self, result: CollectionResult) -> None:
        """
        Perform source-specific collection.

        Derived services must implement this method and update the supplied
        ``CollectionResult`` as work is completed.

        Typical updates include::

            result.items_found
            result.items_processed
            result.add_warning(...)
            result.add_error(...)
            result.set_metadata(...)
        """

        raise NotImplementedError

    def after_collect(self, result: CollectionResult) -> None:
        """
        Finalise collection.

        Derived services may override this hook to close resources, remove
        temporary data or calculate final metadata.

        This hook runs even when preparation or collection raises an
        exception.

        The default implementation performs no action.
        """

        del result


__all__ = ["BaseCollectionService"]