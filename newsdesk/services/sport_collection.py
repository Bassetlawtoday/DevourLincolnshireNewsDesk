"""
Sport story collection service.

This module keeps sports-source collection, source-image handling and
editorial processing outside the Sport Intelligence user interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
from typing import Any

from editorial.gatekeeper import EditorialGatekeeper
from newsdesk.publish_result import PublishResult
from newsdesk.services.image_service import ImageService
from newsdesk.sports.clubs import default_club_scrapers
from newsdesk.sports.rss.bbc_cricket import BBCCricketScraper
from newsdesk.sports.rss.bbc_football import BBCFootballScraper
from newsdesk.sports.rss.bbc_motorsport import BBCMotorsportScraper
from newsdesk.sports.rss.bbc_rugby_league import BBCRugbyLeagueScraper
from newsdesk.sports.rss.bbc_rugby_union import BBCRugbyUnionScraper
from newsdesk.sports.sport_scraper import SportScraper
from newsdesk.sports.websites import default_website_scrapers
from newsdesk.story import Story


SportScraperFactory = Callable[[], Any]
ImageServiceFactory = Callable[[], Any]


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SportCollectionResult:
    """Outcome of one Sport Intelligence collection run."""

    stories: list[Story] = field(default_factory=list)
    visible_stories: list[Story] = field(default_factory=list)
    hidden_stories: list[Story] = field(default_factory=list)
    publish_results: dict[int, PublishResult] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    image_errors: list[str] = field(default_factory=list)

    @property
    def collected_count(self) -> int:
        return len(self.stories)

    @property
    def visible_count(self) -> int:
        return len(self.visible_stories)

    @property
    def hidden_count(self) -> int:
        return len(self.hidden_stories)

    @property
    def processed_count(self) -> int:
        return len(self.publish_results)

    @property
    def image_count(self) -> int:
        return sum(
            1
            for story in self.visible_stories
            if story.has_local_image and not story.image_is_fallback
        )

    @property
    def fallback_image_count(self) -> int:
        return sum(
            1
            for story in self.visible_stories
            if story.has_local_image and story.image_is_fallback
        )

    @property
    def successful(self) -> bool:
        return not self.errors


class SportCollectionService:
    """Collect, enrich and process SportDesk stories."""

    FALLBACK_TITLE = "Sport Intelligence"

    def __init__(
        self,
        scraper_factory: SportScraperFactory | None = None,
        image_service_factory: ImageServiceFactory | None = None,
    ) -> None:
        self.scraper_factory = (
            scraper_factory or self._default_scraper_factory
        )
        self.image_service_factory = (
            image_service_factory or self._default_image_service_factory
        )

    def collect(self) -> SportCollectionResult:
        """Collect stories, classify them and create publishing outputs."""

        scraper = None
        result = SportCollectionResult()

        try:
            scraper = self.scraper_factory()
            image_service = self.image_service_factory()

            stories = list(
                scraper.get_stories(
                    refresh=True,
                    deduplicate=True,
                    continue_on_error=True,
                )
            )
            stories = SportScraper._filter_recent_stories(
                stories,
                stage="collection-service-input",
            )

            gatekeeper = EditorialGatekeeper(max_age_days=14)
            visible_stories, hidden_stories = gatekeeper.classify(stories)

            result.stories = stories
            result.visible_stories = list(visible_stories)
            result.hidden_stories = list(hidden_stories)

            report = getattr(scraper, "last_report", None)
            if report is not None:
                for source_error in report.errors:
                    result.errors.append(
                        f"{source_error.source_name} "
                        f"({source_error.scraper_name}): "
                        f"{source_error.message}"
                    )

            for story in result.stories:
                self._attach_story_image(story, image_service, result)

                try:
                    publish_result = scraper.engine.process(story)
                    result.publish_results[id(story)] = publish_result
                except Exception as error:
                    result.errors.append(
                        f"{self._story_identifier(story)}: {error}"
                    )

            self._apply_final_recency_boundary(result)
            return result

        finally:
            if scraper is not None:
                close_method = getattr(scraper, "close", None)
                if callable(close_method):
                    try:
                        close_method()
                    except Exception:
                        pass

    @staticmethod
    def _apply_final_recency_boundary(
        result: SportCollectionResult,
    ) -> None:
        filtered = SportScraper._filter_recent_stories(
            result.stories,
            stage="collection-service-output",
        )
        kept_ids = {id(story) for story in filtered}
        removed_count = len(result.stories) - len(filtered)

        result.stories = filtered
        result.visible_stories = [
            story
            for story in result.visible_stories
            if id(story) in kept_ids
        ]
        result.hidden_stories = [
            story
            for story in result.hidden_stories
            if id(story) in kept_ids
        ]
        result.publish_results = {
            story_id: publish_result
            for story_id, publish_result in result.publish_results.items()
            if story_id in kept_ids
        }

        if removed_count:
            LOGGER.warning(
                "Final Sport collection recency boundary removed %d "
                "stories after processing.",
                removed_count,
            )

    def _attach_story_image(
        self,
        story: Story,
        image_service: Any,
        result: SportCollectionResult,
    ) -> None:
        """Download or generate one image and attach it to the story."""

        source_url = str(story.image_url or "").strip()

        try:
            asset = image_service.get(
                source_url,
                fallback_title=self.FALLBACK_TITLE,
            )

            story.attach_image(
                asset,
                caption=story.image_caption,
                credit=story.image_credit,
                alt_text=story.image_alt_text,
            )

            story.extras.update(
                {
                    "image_source_url": source_url,
                    "image_download_status": (
                        "fallback"
                        if story.image_is_fallback
                        else "cached"
                        if story.image_cached
                        else "downloaded"
                    ),
                    "image_credit_required": bool(
                        source_url and story.image_credit
                    ),
                }
            )

            if story.image_error:
                result.image_errors.append(
                    f"{self._story_identifier(story)}: "
                    f"{story.image_error}"
                )

        except Exception as error:
            story.image_error = str(error)
            story.extras.update(
                {
                    "image_source_url": source_url,
                    "image_download_status": "failed",
                    "image_credit_required": bool(
                        source_url and story.image_credit
                    ),
                }
            )
            result.image_errors.append(
                f"{self._story_identifier(story)}: {error}"
            )

    @staticmethod
    def _story_identifier(story: Story) -> str:
        return (
            str(story.title or "").strip()
            or str(story.url or "").strip()
            or "Untitled sport story"
        )

    @staticmethod
    def _default_scraper_factory() -> SportScraper:
        sources = [
            BBCFootballScraper(),
            BBCCricketScraper(),
            BBCRugbyUnionScraper(),
            BBCRugbyLeagueScraper(),
            BBCMotorsportScraper(),
            *default_club_scrapers(),
            *default_website_scrapers(),
        ]
        return SportScraper(sources=sources)

    @staticmethod
    def _default_image_service_factory() -> ImageService:
        return ImageService()


__all__ = [
    "SportCollectionResult",
    "SportCollectionService",
]
