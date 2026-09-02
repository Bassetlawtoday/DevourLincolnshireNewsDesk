"""
Sport story collection service.

This module keeps sports-source collection, source-image handling and
editorial processing outside the Sport Intelligence user interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

from newsdesk.publish_result import PublishResult
from newsdesk.services.image_service import ImageService
from newsdesk.services.sport_article_service import SportArticleService
from newsdesk.sports.media_policy import is_still_image_url, is_video_story
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
    source_health: list[dict[str, Any]] = field(default_factory=list)

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

    FALLBACK_TITLE = "Devour Lincolnshire – Sport Intelligence"

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

            video_count = sum(1 for story in stories if is_video_story(story))
            stories = [story for story in stories if not is_video_story(story)]
            if video_count:
                LOGGER.info(
                    "Excluded %d Sport video items; Sport accepts articles and still photographs only.",
                    video_count,
                )

            result.stories = stories
            result.visible_stories = list(stories)
            result.hidden_stories = []

            report = getattr(scraper, "last_report", None)
            if report is not None:
                result.source_health = [
                    {
                        "source_name": outcome.source_name,
                        "scraper_name": outcome.scraper_name,
                        "status": outcome.status,
                        "story_count": outcome.story_count,
                        "message": outcome.message,
                    }
                    for outcome in report.outcomes
                ]
                for source_error in report.errors:
                    result.errors.append(
                        f"{source_error.source_name} "
                        f"({source_error.scraper_name}): "
                        f"{source_error.message}"
                    )

            # Enrichment must precede fallback selection.  Otherwise a real
            # article photograph discovered later can be masked by a holding
            # image created from an empty listing-level image field.
            stories_requiring_media = [
                story
                for story in result.stories
                if not is_still_image_url(story.image_url)
                or story.image_is_fallback
            ]
            with ThreadPoolExecutor(
                max_workers=min(8, max(1, len(stories_requiring_media))),
                thread_name_prefix="sport-enrichment",
            ) as enrichment_executor:
                list(
                    enrichment_executor.map(
                        lambda story: self._enrich_story_media(story, result),
                        stories_requiring_media,
                    )
                )

            # Image hosts vary widely in speed. Fetch several independently so
            # one blocked CDN cannot make the Sport window look frozen.
            with ThreadPoolExecutor(
                max_workers=min(8, max(1, len(result.stories))),
                thread_name_prefix="sport-image",
            ) as image_executor:
                list(
                    image_executor.map(
                        lambda story: self._attach_story_image(
                            story, image_service, result
                        ),
                        result.stories,
                    )
                )

            for story in result.stories:
                try:
                    publish_result = scraper.engine.process(story)
                    result.publish_results[id(story)] = publish_result
                except Exception as error:
                    result.errors.append(
                        f"{self._story_identifier(story)}: {error}"
                    )

            self._apply_final_recency_boundary(result)
            self._write_source_health(result)
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
            require_date=True,
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

        if source_url and not is_still_image_url(source_url):
            story.extras["rejected_media_url"] = source_url
            story.image_url = ""
            source_url = ""

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
    def _enrich_story_media(
        story: Story,
        result: SportCollectionResult,
    ) -> None:
        try:
            service = SportArticleService(timeout=15.0)
            service.enrich(story)
        except Exception as error:
            result.image_errors.append(
                f"{SportCollectionService._story_identifier(story)}: "
                f"article media enrichment failed: {error}"
            )

    @staticmethod
    def _write_source_health(result: SportCollectionResult) -> None:
        """Persist the complete latest source outcome report for inspection."""

        target = Path(__file__).resolve().parents[2] / "data" / "sport_source_health.json"
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "sources": len(result.source_health),
                "yielding": sum(1 for row in result.source_health if row["status"] == "yielding"),
                "no_stories": sum(1 for row in result.source_health if row["status"] == "no-stories"),
                "failed": sum(1 for row in result.source_health if row["status"] == "failed"),
            },
            "sources": result.source_health,
        }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(target)
        except OSError:
            LOGGER.exception("Could not write Sport source health report.")

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
            *default_website_scrapers(),
        ]
        return SportScraper(sources=sources)

    @staticmethod
    def _default_image_service_factory() -> ImageService:
        return ImageService(timeout=12.0)


__all__ = [
    "SportCollectionResult",
    "SportCollectionService",
]
