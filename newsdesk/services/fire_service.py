"""
Fire and rescue story collection service.

This module keeps scraper, source-image collection and editorial-processing
work outside the Fire Intelligence user interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from newsdesk.publish_result import PublishResult
from newsdesk.services.image_service import ImageService
from newsdesk.sources.fire_scraper import (
    DEFAULT_MAX_AGE_DAYS,
    FUTURE_ALLOWANCE_HOURS,
    FireScraper,
    _fire_recency_rejection_reason,
)
from newsdesk.story import Story
from newsdesk.sources.managed_websites import collect_managed_websites


FireScraperFactory = Callable[[], Any]
ImageServiceFactory = Callable[[], Any]
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FireCollectionResult:
    """Outcome of one Fire Intelligence collection run."""

    stories: list[Story] = field(default_factory=list)
    publish_results: dict[int, PublishResult] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    image_errors: list[str] = field(default_factory=list)

    @property
    def collected_count(self) -> int:
        return len(self.stories)

    @property
    def processed_count(self) -> int:
        return len(self.publish_results)

    @property
    def image_count(self) -> int:
        """Number of stories with a valid non-placeholder local image."""

        return sum(
            1
            for story in self.stories
            if story.has_local_image and not story.image_is_fallback
        )

    @property
    def fallback_image_count(self) -> int:
        """Number of stories using the generated fallback image."""

        return sum(
            1
            for story in self.stories
            if story.has_local_image and story.image_is_fallback
        )

    @property
    def successful(self) -> bool:
        return not self.errors


class FireCollectionService:
    """
    Collect, enrich and process fire and rescue stories.

    The scraper extracts the source image address and editorial image
    metadata. The shared ImageService then downloads, validates and caches
    the image before the Story is passed to StoryEngine.

    Image failure is deliberately non-fatal. A generated fallback is attached
    and the reason is recorded in ``image_errors`` and on the Story itself.
    """

    FALLBACK_TITLE = "Fire Intelligence"

    def __init__(
        self,
        scraper_factory: FireScraperFactory | None = None,
        image_service_factory: ImageServiceFactory | None = None,
    ) -> None:
        self.scraper_factory = (
            scraper_factory
            or self._default_scraper_factory
        )
        self.image_service_factory = (
            image_service_factory
            or self._default_image_service_factory
        )

    def collect(self) -> FireCollectionResult:
        """Collect stories, attach images and process editorial outputs."""

        scraper = None
        result = FireCollectionResult()

        try:
            scraper = self.scraper_factory()
            image_service = self.image_service_factory()

            collected_stories = list(scraper.fetch_latest_news())
            managed_stories, managed_errors = collect_managed_websites("fire")
            collected_stories.extend(managed_stories)
            result.errors.extend(managed_errors)
            stories = self._filter_recent_stories(
                collected_stories,
                stage="collection-service-final",
            )
            result.stories = stories

            for story in stories:
                self._ensure_story_summary(story)
                self._attach_story_image(
                    story,
                    image_service,
                    result,
                )

                try:
                    publish_result = scraper.engine.process(story)
                    result.publish_results[id(story)] = publish_result
                except Exception as error:
                    identifier = self._story_identifier(story)
                    result.errors.append(f"{identifier}: {error}")

            return result

        finally:
            if scraper is not None:
                close_method = getattr(scraper, "close", None)

                if callable(close_method):
                    try:
                        close_method()
                    except Exception:
                        # Collection has already completed or raised its
                        # original error. Cleanup must not hide that error.
                        pass

    @staticmethod
    def _filter_recent_stories(
        stories: list[Story],
        *,
        now: datetime | None = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        stage: str,
    ) -> list[Story]:
        """Apply the authoritative Fire publication-date boundary."""

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        cutoff = current - timedelta(days=max_age_days)
        future_limit = current + timedelta(hours=FUTURE_ALLOWANCE_HOURS)
        retained: list[Story] = []
        for story in stories:
            parsed, reason = _fire_recency_rejection_reason(
                story.published,
                now=current,
                max_age_days=max_age_days,
            )
            if reason is None:
                retained.append(story)
                continue
            LOGGER.debug(
                "Fire recency rejection title=%r source=%r raw_date=%r "
                "parsed_date=%s cutoff=%s future_limit=%s stage=%s reason=%s",
                story.title,
                story.source,
                story.published,
                parsed,
                cutoff,
                future_limit,
                stage,
                reason,
            )
        LOGGER.info(
            "Fire recency filter at %s: kept %s of %s stories; rejected %s.",
            stage,
            len(retained),
            len(stories),
            len(stories) - len(retained),
        )
        return retained

    @classmethod
    def _ensure_story_summary(cls, story: Story) -> None:
        """Preserve an existing summary or generate one once from the body."""

        existing = cls._meaningful_summary_text(story.summary)
        if existing:
            story.summary = existing
            return
        extras = getattr(story, "extras", {}) or {}
        for key in ("standfirst", "description", "source_description", "meta_description"):
            candidate = cls._meaningful_summary_text(extras.get(key, ""))
            if candidate:
                story.summary = candidate
                return

        paragraphs: list[str] = []
        seen: set[str] = set()
        for value in re.split(r"\n\s*\n|\r\n\s*\r\n", str(story.body or "")):
            cleaned = cls._meaningful_summary_text(value)
            key = cleaned.casefold()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            paragraphs.append(cleaned)

        selected: list[str] = []
        words = 0
        for paragraph in paragraphs:
            if selected and words >= 30:
                break
            selected.append(paragraph)
            words += len(paragraph.split())
            if words >= 70:
                break
        story.summary = cls._trim_summary(" ".join(selected), 70)

    @staticmethod
    def _meaningful_summary_text(value: object) -> str:
        text = " ".join(str(value or "").replace("\xa0", " ").split())
        if not text:
            return ""
        lowered = text.casefold().strip(" :.-")
        if any(
            lowered.startswith(prefix)
            for prefix in (
                "share this",
                "subscribe",
                "sign up",
                "image caption",
                "image credit",
                "photo credit",
                "cookie",
                "for general enquiries",
                "in an emergency call",
                "related content",
                "read more",
            )
        ):
            return ""
        if len(text.split()) <= 8 and not re.search(r"[.!?]$", text):
            return ""
        if text.startswith(("\"", "“", "‘", "'")) and text.endswith(("\"", "”", "’", "'")):
            return ""
        return text

    @staticmethod
    def _trim_summary(text: str, maximum_words: int) -> str:
        words = text.split()
        if len(words) <= maximum_words:
            return text.strip()
        candidate = " ".join(words[:maximum_words]).strip()
        ends = [match.end() for match in re.finditer(r"[.!?](?=\s|$)", candidate)]
        if ends:
            complete = candidate[: ends[-1]].strip()
            if len(complete.split()) >= 30:
                return complete
        return candidate.rstrip(" ,;:-") + "…"

    def _attach_story_image(
        self,
        story: Story,
        image_service: Any,
        result: FireCollectionResult,
    ) -> None:
        """Download/cache one source image and attach it to the Story."""

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
            # A custom or future image service should not be able to prevent
            # the news collection itself from completing.
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
            or "Untitled fire story"
        )

    @staticmethod
    def _default_scraper_factory() -> FireScraper:
        return FireScraper(limit=20)

    @staticmethod
    def _default_image_service_factory() -> ImageService:
        return ImageService()


__all__ = [
    "FireCollectionResult",
    "FireCollectionService",
]
