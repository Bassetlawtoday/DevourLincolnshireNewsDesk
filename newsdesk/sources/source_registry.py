"""Registry for creating scraper instances from source configuration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class SourceRegistryError(RuntimeError):
    """Base error raised by the source registry."""


class UnknownSourceTypeError(SourceRegistryError):
    """Raised when no scraper is registered for a source type."""


class DuplicateSourceTypeError(SourceRegistryError):
    """Raised when a source type is registered more than once."""


ScraperFactory = Callable[[dict[str, Any]], Any]


class SourceRegistry:
    """Maps source types to scraper factories."""

    def __init__(self) -> None:
        self._factories: dict[str, ScraperFactory] = {}

    def register(
        self,
        source_type: str,
        factory: ScraperFactory,
    ) -> None:
        """Register a scraper factory for a source type."""

        normalised_type = self._normalise_source_type(source_type)

        if not normalised_type:
            raise ValueError("Source type cannot be empty.")

        if normalised_type in self._factories:
            raise DuplicateSourceTypeError(
                f"Source type already registered: {normalised_type}"
            )

        if not callable(factory):
            raise TypeError("Scraper factory must be callable.")

        self._factories[normalised_type] = factory

    def create(self, source: dict[str, Any]) -> Any:
        """Create a scraper for a source configuration."""

        if not isinstance(source, dict):
            raise TypeError("Source configuration must be a dictionary.")

        source_type = self._normalise_source_type(
            str(source.get("type", ""))
        )

        if not source_type:
            raise UnknownSourceTypeError(
                "Source configuration does not contain a valid 'type'."
            )

        try:
            factory = self._factories[source_type]
        except KeyError as error:
            raise UnknownSourceTypeError(
                f"No scraper registered for source type: {source_type}"
            ) from error

        return factory(source)

    def is_registered(self, source_type: str) -> bool:
        """Return whether a source type has been registered."""

        normalised_type = self._normalise_source_type(source_type)
        return normalised_type in self._factories

    def registered_types(self) -> tuple[str, ...]:
        """Return registered source types in alphabetical order."""

        return tuple(sorted(self._factories))

    @staticmethod
    def _normalise_source_type(source_type: str) -> str:
        return source_type.strip().lower()