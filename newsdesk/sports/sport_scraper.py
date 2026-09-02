"""
newsdesk.sources.sport_scraper

SportDesk collection orchestrator for Devour Lincolnshire NewsDesk.

This framework deliberately contains no live source implementations yet.
Individual BBC feeds and official club websites will be implemented as
separate scraper classes and registered with SportScraper.
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import re
from typing import Any
from urllib.parse import urlparse

from newsdesk.publish_result import PublishResult
from newsdesk.story import Story
from newsdesk.story_engine import StoryEngine
from newsdesk.geography.lincolnshire import story_matches_lincolnshire


LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_AGE_DAYS = 7


@dataclass(slots=True)
class SportSourceError:
    """Details of a sports source that could not be collected."""

    source_name: str
    scraper_name: str
    message: str


@dataclass(slots=True)
class SportSourceOutcome:
    """Yield and health of one configured source in the latest run."""

    source_name: str
    scraper_name: str
    status: str
    story_count: int = 0
    message: str = ""


@dataclass(slots=True)
class SportScrapeReport:
    """Summary of the most recent SportDesk collection run."""

    sources_selected: int = 0
    sources_completed: int = 0
    stories_found: int = 0
    stories_returned: int = 0
    errors: list[SportSourceError] = field(default_factory=list)
    outcomes: list[SportSourceOutcome] = field(default_factory=list)
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None

    @property
    def successful(self) -> bool:
        return not self.errors

    @property
    def duration_seconds(self) -> float:
        if self.completed_at is None:
            return 0.0

        return max(
            0.0,
            (self.completed_at - self.started_at).total_seconds(),
        )


class SportScraper:
    """
    Collect and merge stories from independent sports source scrapers.

    A registered source scraper must expose ``get_stories()`` and return
    NewsDesk ``Story`` objects. Full ``BaseScraper`` implementations are
    supported directly, while lightweight test or future source adapters may
    provide the same public method.

    SportScraper is an orchestrator rather than a ``BaseScraper`` subclass
    because SportDesk has many independent source URLs rather than one page.
    """

    def __init__(
        self,
        sources: Iterable[Any] | None = None,
        *,
        engine: StoryEngine | None = None,
    ) -> None:
        self.engine = engine or StoryEngine(
            strict_validation=False,
            strict_formatting=False,
        )
        self._sources: list[Any] = []
        self._stories: list[Story] = []
        self._results: list[PublishResult] = []
        self._last_report: SportScrapeReport | None = None

        for source in sources or ():
            self.register_source(source)

    def register_source(self, scraper: Any) -> None:
        """Register one sports source scraper."""

        if scraper is None:
            raise TypeError("scraper cannot be None.")

        get_stories = getattr(scraper, "get_stories", None)

        if not callable(get_stories):
            raise TypeError(
                f"{type(scraper).__name__} does not provide get_stories()."
            )

        if any(existing is scraper for existing in self._sources):
            raise ValueError("The same scraper instance is already registered.")

        self._sources.append(scraper)

    def register_sources(self, scrapers: Iterable[Any]) -> None:
        """Register several sports source scrapers in order."""

        for scraper in scrapers:
            self.register_source(scraper)

    def remove_source(self, scraper: Any) -> bool:
        """
        Remove a registered scraper instance.

        Return True when it was registered, otherwise False.
        """

        for index, existing in enumerate(self._sources):
            if existing is scraper:
                del self._sources[index]
                return True

        return False

    @property
    def sources(self) -> tuple[Any, ...]:
        """Return registered source scrapers in collection order."""

        return tuple(self._sources)

    @property
    def stories(self) -> list[Story]:
        return list(self._stories)

    @property
    def publish_results(self) -> list[PublishResult]:
        return list(self._results)

    @property
    def last_report(self) -> SportScrapeReport | None:
        return self._last_report

    def get_stories(
        self,
        *,
        refresh: bool = True,
        deduplicate: bool = True,
        continue_on_error: bool = True,
    ) -> list[Story]:
        """Collect stories from every registered sports source."""

        if not refresh and self._stories:
            self._stories = self._filter_recent_stories(
                self._stories,
                stage="combined-cache-read",
            )
            return list(self._stories)

        report = SportScrapeReport(
            sources_selected=len(self._sources),
        )
        collected: list[Story] = []

        try:
            worker_count = min(12, max(1, len(self._sources)))
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="sport-source",
            ) as executor:
                futures = {
                    executor.submit(
                        self._collect_source,
                        scraper,
                        refresh=refresh,
                        deduplicate=deduplicate,
                    ): scraper
                    for scraper in self._sources
                }

                for future in as_completed(futures):
                    scraper = futures[future]
                    source_name = self._source_name(scraper)

                    try:
                        stories = future.result()

                        if self._requires_lincolnshire_filter(scraper):
                            retained = []
                            for story in stories:
                                match = story_matches_lincolnshire(story)
                                if not match.matched:
                                    continue
                                story.extras.setdefault(
                                    "geographic_filter", "lincolnshire"
                                )
                                story.extras.setdefault(
                                    "geographic_matches", list(match.places)
                                )
                                retained.append(story)
                            stories = retained

                        for story in stories:
                            self._apply_sport_metadata(
                                story,
                                source_name=source_name,
                                scraper=scraper,
                            )
                            story.extras.setdefault(
                                "collector_route",
                                str(
                                    getattr(scraper, "definition", None).metadata.get(
                                        "collector_route", "specialist"
                                    )
                                    if getattr(scraper, "definition", None) is not None
                                    else "specialist"
                                ),
                            )

                        collected.extend(stories)
                        report.sources_completed += 1
                        report.stories_found += len(stories)
                        report.outcomes.append(
                            SportSourceOutcome(
                                source_name=source_name,
                                scraper_name=type(scraper).__name__,
                                status="yielding" if stories else "no-stories",
                                story_count=len(stories),
                                message=(
                                    "Stories collected."
                                    if stories
                                    else "Source reached successfully; no stories were accepted."
                                ),
                            )
                        )

                    except Exception as error:
                        LOGGER.exception(
                            "Could not collect sports stories from %s.",
                            source_name,
                        )

                        report.errors.append(
                            SportSourceError(
                                source_name=source_name,
                                scraper_name=type(scraper).__name__,
                                message=str(error),
                            )
                        )
                        report.outcomes.append(
                            SportSourceOutcome(
                                source_name=source_name,
                                scraper_name=type(scraper).__name__,
                                status="failed",
                                message=str(error),
                            )
                        )

                        if not continue_on_error:
                            for pending in futures:
                                pending.cancel()
                            raise

            if deduplicate:
                collected = self._deduplicate_stories(collected)

            collected = self._filter_recent_stories(
                collected,
                stage="post-collection-deduplication",
            )
            self._stories = collected
            report.stories_returned = len(collected)

            return list(self._stories)

        finally:
            report.completed_at = datetime.now(timezone.utc)
            self._last_report = report

    def process(
        self,
        stories: Iterable[Story] | None = None,
        *,
        refresh: bool = True,
        continue_on_error: bool = True,
    ) -> list[PublishResult]:
        """Process collected sports stories through StoryEngine."""

        source_stories = (
            self._filter_recent_stories(
                stories,
                stage="explicit-process-input",
            )
            if stories is not None
            else self.get_stories(
                refresh=refresh,
                continue_on_error=continue_on_error,
            )
        )

        results: list[PublishResult] = []

        for story in source_stories:
            try:
                results.append(self.engine.process(story))
            except Exception:
                LOGGER.exception(
                    "Could not process sports story %s.",
                    story.title.strip() or story.url.strip() or "Untitled",
                )

                if not continue_on_error:
                    raise

        self._results = results
        return list(results)

    @classmethod
    def _filter_recent_stories(
        cls,
        stories: Iterable[Story],
        *,
        now: datetime | None = None,
        stage: str = "sport-orchestration",
        require_date: bool = False,
    ) -> list[Story]:
        candidates = list(stories)
        current_time = cls._aware_utc(now or datetime.now(timezone.utc))
        future_limit = current_time + timedelta(hours=24)
        kept: list[Story] = []

        for story in candidates:
            raw_published = story.published
            parsed_published = cls._parse_publication_date(raw_published)
            reason = cls._recency_rejection_reason(
                raw_published=raw_published,
                parsed_published=parsed_published,
                future_limit=future_limit,
                max_age_days=cls._max_age_days(),
                require_date=require_date,
            )

            if reason:
                LOGGER.debug(
                    "Rejected sport story title=%r source=%r "
                    "raw publication date=%r parsed publication date=%s "
                    "pipeline stage=%s reason=%s",
                    story.title,
                    story.source,
                    raw_published,
                    (
                        parsed_published.isoformat()
                        if parsed_published is not None
                        else "unavailable"
                    ),
                    stage,
                    reason,
                )
                continue

            kept.append(story)

        LOGGER.info(
            "Global sport date-safety filter at %s: kept %d of %d stories; "
            "rejected %d.",
            stage,
            len(kept),
            len(candidates),
            len(candidates) - len(kept),
        )
        return kept

    @classmethod
    def _max_age_days(cls) -> int | None:
        return DEFAULT_MAX_AGE_DAYS

    @staticmethod
    def _recency_rejection_reason(
        *,
        raw_published: object,
        parsed_published: datetime | None,
        future_limit: datetime,
        max_age_days: int | None,
        require_date: bool = False,
    ) -> str:
        if raw_published is None or not str(raw_published).strip():
            return "story-date-missing" if require_date else ""
        if parsed_published is None:
            return "story-date-invalid" if require_date else ""
        if parsed_published > future_limit:
            return "story-date-in-future"
        if max_age_days is not None:
            cutoff = future_limit - timedelta(hours=24, days=max_age_days)
            if parsed_published < cutoff:
                return "story-older-than-seven-days"
        return ""

    @classmethod
    def _parse_publication_date(cls, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return cls._aware_utc(value)
        if isinstance(value, date):
            return datetime(
                value.year,
                value.month,
                value.day,
                tzinfo=timezone.utc,
            )

        text = " ".join(str(value or "").split()).strip()
        if not text:
            return None

        try:
            return cls._aware_utc(
                datetime.fromisoformat(text.replace("Z", "+00:00"))
            )
        except (TypeError, ValueError):
            pass

        try:
            return cls._aware_utc(parsedate_to_datetime(text))
        except (TypeError, ValueError, OverflowError):
            pass

        without_ordinal = re.sub(
            r"(?<=\d)(?:st|nd|rd|th)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )
        for date_format in (
            "%d %B %Y",
            "%d %b %Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
        ):
            try:
                parsed = datetime.strptime(without_ordinal, date_format)
            except ValueError:
                continue
            return parsed.replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _is_undated_standalone_story(story: Story) -> bool:
        extras = story.extras if isinstance(story.extras, dict) else {}
        return bool(
            str(extras.get("source_kind", "")).casefold()
            == "generic_website"
            and str(extras.get("article_content_status", "")).casefold()
            == "complete"
            and urlparse(str(story.url or "")).fragment
        )

    def run(
        self,
        *,
        refresh: bool = True,
        continue_on_error: bool = True,
    ) -> list[PublishResult]:
        """Collect and process all registered sports sources."""

        return self.process(
            refresh=refresh,
            continue_on_error=continue_on_error,
        )

    def clear(self) -> None:
        """Clear SportDesk caches and clear each registered scraper."""

        self._stories.clear()
        self._results.clear()
        self._last_report = None

        for scraper in self._sources:
            clear_method = getattr(scraper, "clear", None)

            if callable(clear_method):
                clear_method()

    def close(self) -> None:
        """Close any registered source that owns external resources."""

        for scraper in self._sources:
            close_method = getattr(scraper, "close", None)

            if not callable(close_method):
                continue

            try:
                close_method()
            except Exception:
                LOGGER.debug(
                    "Sports source %s did not close cleanly.",
                    self._source_name(scraper),
                    exc_info=True,
                )

    def diagnostics(self) -> dict[str, Any]:
        """Return framework and latest-run diagnostics for the UI or console."""

        report = self._last_report

        return {
            "registered_sources": len(self._sources),
            "source_names": [
                self._source_name(scraper)
                for scraper in self._sources
            ],
            "cached_stories": len(self._stories),
            "cached_publish_results": len(self._results),
            "last_run": None
            if report is None
            else {
                "successful": report.successful,
                "sources_selected": report.sources_selected,
                "sources_completed": report.sources_completed,
                "stories_found": report.stories_found,
                "stories_returned": report.stories_returned,
                "duration_seconds": report.duration_seconds,
                "errors": [
                    {
                        "source_name": error.source_name,
                        "scraper_name": error.scraper_name,
                        "message": error.message,
                    }
                    for error in report.errors
                ],
                "outcomes": [
                    {
                        "source_name": outcome.source_name,
                        "scraper_name": outcome.scraper_name,
                        "status": outcome.status,
                        "story_count": outcome.story_count,
                        "message": outcome.message,
                    }
                    for outcome in report.outcomes
                ],
            },
        }

    def __enter__(self) -> "SportScraper":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @staticmethod
    def _collect_source(
        scraper: Any,
        *,
        refresh: bool,
        deduplicate: bool,
    ) -> list[Story]:
        method = getattr(scraper, "get_stories")

        try:
            stories = method(
                refresh=refresh,
                deduplicate=deduplicate,
            )
        except TypeError:
            stories = method()

        result = list(stories)

        for item in result:
            if not isinstance(item, Story):
                raise TypeError(
                    f"{type(scraper).__name__}.get_stories() returned "
                    f"{type(item).__name__}; expected Story."
                )

        return result

    @staticmethod
    def _source_name(scraper: Any) -> str:
        value = str(
            getattr(scraper, "source_name", "")
            or getattr(scraper, "name", "")
            or type(scraper).__name__
        ).strip()

        return value or type(scraper).__name__

    @staticmethod
    def _requires_lincolnshire_filter(scraper: Any) -> bool:
        """Apply the shared county boundary to broad regional/national feeds."""

        definition = getattr(scraper, "definition", None)
        metadata = getattr(definition, "metadata", {}) or {}
        configured = str(metadata.get("geographic_filter", "")).casefold()
        if configured in {"lincolnshire", "lincolnshire-strict"}:
            return True

        # BBC sport feeds are national. Retaining them without a county match
        # overwhelms local club and governing-body reporting.
        return type(scraper).__name__.startswith("BBC")

    @staticmethod
    def _apply_sport_metadata(
        story: Story,
        *,
        source_name: str,
        scraper: Any,
    ) -> None:
        if not story.source.strip():
            story.source = source_name

        if not story.category.strip():
            story.category = "Sport"

        story.extras.setdefault("module_profile", "sport")
        story.extras.setdefault(
            "sport_source_scraper",
            type(scraper).__name__,
        )

    @classmethod
    def _deduplicate_stories(
        cls,
        stories: Iterable[Story],
    ) -> list[Story]:
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
        story_id = str(story.story_id or "").strip().casefold()

        if story_id:
            return f"id:{story_id}"

        url = story.url.strip().casefold().rstrip("/")

        if url:
            return f"url:{url}"

        title = " ".join(story.title.casefold().split())
        published = str(story.published or "").strip().casefold()

        return f"title:{title}|published:{published}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"sources={len(self._sources)}, "
            f"stories={len(self._stories)})"
        )


__all__ = [
    "SportScrapeReport",
    "SportScraper",
    "SportSourceError",
]
