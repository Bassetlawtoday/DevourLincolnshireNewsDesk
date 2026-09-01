"""
Collect stories from configured NewsDesk sources.

The collector coordinates SourceLoader and SourceRegistry. Individual source
implementations only need to expose get_stories().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from newsdesk.sources.source_loader import SourceLoader
from newsdesk.sources.source_registry import SourceRegistry
from newsdesk.story import Story


@dataclass(slots=True)
class SourceCollectionError:
    """Details of a source that could not be collected."""

    source_id: str
    source_name: str
    message: str


@dataclass(slots=True)
class SourceCollectionReport:
    """Summary of a collection run."""

    profile: str
    sources_selected: int = 0
    sources_completed: int = 0
    stories_found: int = 0
    stories_returned: int = 0
    errors: list[SourceCollectionError] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        return not self.errors


class SourceCollector:
    """Collect and merge stories for one NewsDesk module profile."""

    def __init__(
        self,
        registry: SourceRegistry,
        loader: SourceLoader | None = None,
    ) -> None:
        self.registry = registry
        self.loader = loader or SourceLoader()
        self._last_report: SourceCollectionReport | None = None

    @property
    def last_report(self) -> SourceCollectionReport | None:
        return self._last_report

    def collect(
        self,
        profile: str,
        *,
        refresh: bool = True,
        deduplicate: bool = True,
        continue_on_error: bool = True,
    ) -> list[Story]:
        """
        Collect enabled sources matching a NewsDesk module profile.

        A source matches when either its module_profile or category equals the
        requested profile.
        """

        normalised_profile = self._normalise(profile)

        if not normalised_profile:
            raise ValueError("profile cannot be empty.")

        sources = [
            source
            for source in self.loader.load()
            if self._matches_profile(source, normalised_profile)
        ]

        report = SourceCollectionReport(
            profile=normalised_profile,
            sources_selected=len(sources),
        )

        collected: list[Story] = []

        for source in sources:
            source_id = str(source.get("id", "")).strip()
            source_name = str(
                source.get("name", source_id)
            ).strip()

            try:
                scraper = self.registry.create(source)

                stories = self._get_stories(
                    scraper,
                    refresh=refresh,
                    deduplicate=deduplicate,
                )

                for story in stories:
                    self._apply_source_metadata(
                        story,
                        source=source,
                        profile=normalised_profile,
                    )

                collected.extend(stories)

                report.sources_completed += 1
                report.stories_found += len(stories)

            except Exception as error:
                report.errors.append(
                    SourceCollectionError(
                        source_id=source_id,
                        source_name=source_name,
                        message=str(error),
                    )
                )

                if not continue_on_error:
                    self._last_report = report
                    raise

        if deduplicate:
            collected = self._deduplicate(collected)

        report.stories_returned = len(collected)
        self._last_report = report

        return collected

    @staticmethod
    def _get_stories(
        scraper: Any,
        *,
        refresh: bool,
        deduplicate: bool,
    ) -> list[Story]:
        """Call get_stories() on either full or lightweight scrapers."""

        method = getattr(scraper, "get_stories", None)

        if not callable(method):
            raise TypeError(
                f"{type(scraper).__name__} does not provide "
                "get_stories()."
            )

        try:
            stories = method(
                refresh=refresh,
                deduplicate=deduplicate,
            )

        except TypeError:
            # The current FacebookScraper exposes get_stories()
            # without refresh or deduplicate arguments.
            stories = method()

        result = list(stories)

        for item in result:
            if not isinstance(item, Story):
                raise TypeError(
                    f"{type(scraper).__name__}.get_stories() returned "
                    f"{type(item).__name__}; expected Story."
                )

        return result

    @classmethod
    def _matches_profile(
        cls,
        source: dict[str, Any],
        profile: str,
    ) -> bool:
        module_profile = cls._normalise(
            source.get("module_profile", "")
        )

        category = cls._normalise(
            source.get("category", "")
        )

        return profile in {
            module_profile,
            category,
        }

    @staticmethod
    def _apply_source_metadata(
        story: Story,
        *,
        source: dict[str, Any],
        profile: str,
    ) -> None:
        """Attach configuration metadata to a collected Story."""

        if not story.source.strip():
            story.source = str(
                source.get("name", "")
            ).strip()

        if not story.category.strip():
            story.category = str(
                source.get("category", profile)
            ).strip()

        story.extras.setdefault(
            "source_id",
            source.get("id", ""),
        )

        story.extras.setdefault(
            "module_profile",
            profile,
        )

        story.extras.setdefault(
            "zone",
            source.get("zone", ""),
        )

        story.extras.setdefault(
            "source_type",
            source.get("type", ""),
        )

    @classmethod
    def _deduplicate(
        cls,
        stories: Iterable[Story],
    ) -> list[Story]:
        """Remove duplicate stories returned by different sources."""

        unique: list[Story] = []
        seen: set[str] = set()

        for story in stories:
            key = cls._story_key(story)

            if key in seen:
                continue

            seen.add(key)
            unique.append(story)

        return unique

    @staticmethod
    def _story_key(story: Story) -> str:
        story_id = str(
            story.story_id or ""
        ).strip().casefold()

        if story_id:
            return f"id:{story_id}"

        url = story.url.strip().casefold().rstrip("/")

        if url:
            return f"url:{url}"

        title = " ".join(
            story.title.casefold().split()
        )

        published = str(
            story.published or ""
        ).strip().casefold()

        return (
            f"title:{title}|"
            f"published:{published}"
        )

    @staticmethod
    def _normalise(value: Any) -> str:
        return str(value or "").strip().casefold()


__all__ = [
    "SourceCollectionError",
    "SourceCollectionReport",
    "SourceCollector",
]
