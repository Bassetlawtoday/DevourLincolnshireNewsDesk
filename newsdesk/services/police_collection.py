"""
Police story collection service.

This module keeps scraper, source-image collection and editorial-processing
work outside the Police Intelligence user interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from newsdesk.publish_result import PublishResult
from newsdesk.services.image_service import ImageService
from newsdesk.sources.police_scraper import (
    DEFAULT_MAX_AGE_DAYS,
    FUTURE_ALLOWANCE_HOURS,
    PoliceScraper,
    _police_recency_rejection_reason,
)
from newsdesk.story import Story
from newsdesk.sources.managed_websites import collect_managed_websites
from newsdesk.sources.regional_police import collect_regional_police_sources


PoliceScraperFactory = Callable[[], Any]
ImageServiceFactory = Callable[[], Any]
ProgressCallback = Callable[[dict[str, Any]], None]
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PoliceCollectionResult:
    """Outcome of one Police Intelligence collection run."""

    stories: list[Story] = field(default_factory=list)
    publish_results: dict[int, PublishResult] = field(
        default_factory=dict
    )
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


class PoliceCollectionService:
    """
    Collect, enrich and process police stories.

    The existing Selenium-based PoliceScraper remains responsible for source
    navigation and article extraction. The shared ImageService is invoked
    here, at module-service level, to download, validate and cache one source
    image at a time before each Story is passed to StoryEngine.

    Only lightweight paths and metadata are attached to Story. Image bytes,
    base64 data and binary objects are never passed to StoryEngine.

    Image failure is non-fatal. A generated fallback is attached and the
    reason is recorded in ``image_errors`` and on the Story itself.
    """

    FALLBACK_TITLE = "Police Intelligence"

    def __init__(
        self,
        scraper_factory: PoliceScraperFactory | None = None,
        image_service_factory: ImageServiceFactory | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.scraper_factory = (
            scraper_factory
            or self._default_scraper_factory
        )
        self.image_service_factory = (
            image_service_factory
            or self._default_image_service_factory
        )
        self.progress_callback = progress_callback

    def _progress(self, stage: str, index: int, source: str, story_count: int = 0) -> None:
        if self.progress_callback is not None:
            self.progress_callback({
                "stage": stage,
                "index": index,
                "total": 5,
                "source": source,
                "story_count": story_count,
            })

    def collect(self) -> PoliceCollectionResult:
        """Collect stories, attach images and process editorial outputs."""

        scraper = None
        result = PoliceCollectionResult()

        try:
            scraper = self.scraper_factory()
            image_service = self.image_service_factory()

            self._progress("collecting", 1, "Lincolnshire Police")
            collected_stories = list(
                scraper.fetch_latest_news()
            )
            self._progress("collecting", 2, "Regional police sources", len(collected_stories))
            regional_stories, regional_errors = collect_regional_police_sources()
            collected_stories.extend(regional_stories)
            result.errors.extend(regional_errors)
            self._progress("collecting", 3, "Managed Lincolnshire sources", len(collected_stories))
            managed_stories, managed_errors = collect_managed_websites("police")
            collected_stories.extend(managed_stories)
            result.errors.extend(managed_errors)
            stories = self._filter_recent_stories(
                collected_stories,
                stage="collection-service-final",
            )
            stories = self._deduplicate_stories(stories)

            result.stories = stories

            for story in stories:
                self._ensure_story_summary(story)

            self._progress("images", 4, "Downloading story images", len(stories))
            with ThreadPoolExecutor(
                max_workers=min(6, max(1, len(stories))),
                thread_name_prefix="police-image",
            ) as image_executor:
                list(image_executor.map(
                    lambda story: self._attach_story_image(story, image_service, result),
                    stories,
                ))

            self._progress("processing", 5, "Preparing Social Desk content", len(stories))
            for story in stories:
                try:
                    publish_result = scraper.engine.process(
                        story
                    )

                    result.publish_results[id(story)] = (
                        publish_result
                    )

                except Exception as error:
                    result.errors.append(
                        f"{self._story_identifier(story)}: {error}"
                    )

            return result

        finally:
            if scraper is not None:
                close_method = getattr(
                    scraper,
                    "close",
                    None,
                )

                if callable(close_method):
                    try:
                        close_method()
                    except Exception:
                        # Collection has already completed or raised its
                        # original error. Browser cleanup must not hide it.
                        pass

    @staticmethod
    def _filter_recent_stories(
        stories: list[Story],
        *,
        now: datetime | None = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        stage: str,
    ) -> list[Story]:
        """Apply the authoritative Police publication-date boundary."""

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)
        cutoff = current - timedelta(days=max_age_days)
        future_limit = current + timedelta(hours=FUTURE_ALLOWANCE_HOURS)
        retained: list[Story] = []

        for story in stories:
            parsed, reason = _police_recency_rejection_reason(
                story.published,
                now=current,
                max_age_days=max_age_days,
            )
            if reason is None:
                retained.append(story)
                continue
            LOGGER.debug(
                "Police recency rejection title=%r source=%r raw_date=%r "
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
            "Police recency filter at %s: kept %s of %s stories; rejected %s.",
            stage,
            len(retained),
            len(stories),
            len(stories) - len(retained),
        )
        return retained

    @classmethod
    def _deduplicate_stories(cls, stories: list[Story]) -> list[Story]:
        """Remove cross-source repeats while preferring the fullest story."""

        ranked = sorted(
            enumerate(stories),
            key=lambda pair: (
                str(pair[1].source or "").casefold() != "lincolnshire police",
                -len(str(pair[1].body or "")),
                pair[0],
            ),
        )
        kept: list[tuple[int, Story]] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        for original_index, story in ranked:
            url_key = cls._canonical_story_url(story.url)
            title_key = cls._normalised_story_title(story.title)
            if (url_key and url_key in seen_urls) or (
                title_key and title_key in seen_titles
            ):
                LOGGER.info(
                    "Police duplicate removed title=%r source=%r url=%s",
                    story.title,
                    story.source,
                    story.url,
                )
                continue
            if url_key:
                seen_urls.add(url_key)
            if title_key:
                seen_titles.add(title_key)
            kept.append((original_index, story))
        kept.sort(key=lambda pair: pair[0])
        return [story for _, story in kept]

    @staticmethod
    def _canonical_story_url(value: object) -> str:
        text = str(value or "").strip().casefold()
        text = text.split("#", 1)[0].split("?", 1)[0]
        return text.rstrip("/")

    @staticmethod
    def _normalised_story_title(value: object) -> str:
        text = str(value or "").casefold().replace("’", "'")
        return re.sub(r"[^a-z0-9]+", " ", text).strip()

    @classmethod
    def _ensure_story_summary(cls, story: Story) -> None:
        """Populate Story.summary once without changing the article body."""

        existing = cls._meaningful_summary_text(story.summary)
        if existing:
            story.summary = existing
            return

        extras = getattr(story, "extras", {}) or {}
        for key in (
            "standfirst",
            "description",
            "source_description",
            "meta_description",
        ):
            candidate = cls._meaningful_summary_text(extras.get(key, ""))
            if candidate:
                story.summary = candidate
                return

        story.summary = cls._summary_from_body(story.body)

    @classmethod
    def _summary_from_body(cls, body: object) -> str:
        """Build a factual 30-70 word extract from opening paragraphs."""

        paragraphs: list[str] = []
        seen: set[str] = set()
        for value in re.split(r"\n\s*\n|\r\n\s*\r\n", str(body or "")):
            cleaned = cls._meaningful_summary_text(value)
            key = cleaned.casefold()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            paragraphs.append(cleaned)
        if not paragraphs:
            return ""

        selected: list[str] = []
        word_count = 0
        for paragraph in paragraphs:
            paragraph_words = paragraph.split()
            if selected and word_count >= 30:
                break
            selected.append(paragraph)
            word_count += len(paragraph_words)
            if word_count >= 70:
                break

        return cls._trim_summary(" ".join(selected), maximum_words=70)

    @classmethod
    def _meaningful_summary_text(cls, value: object) -> str:
        text = " ".join(str(value or "").replace("\xa0", " ").split())
        if not text:
            return ""

        lowered = text.casefold().strip(" :.-")
        blocked_prefixes = (
            "allow youtube content",
            "this page contains content provided by",
            "we need your permission",
            "you can use your browser settings",
            "we're not responsible for the content of external sites",
            "we are not responsible for the content of external sites",
            "sorry, there was a technical problem",
            "please try again",
            "watch the video",
            "share this page",
            "sign up",
            "subscribe",
            "image caption",
            "image credit",
            "photo credit",
            "picture credit",
            "read more",
            "related content",
            "main article content",
        )
        if any(lowered.startswith(prefix) for prefix in blocked_prefixes):
            return ""
        if len(text.split()) <= 8 and not re.search(r"[.!?]$", text):
            return ""
        if text.startswith(("\"", "“", "‘", "'")) and text.endswith(
            ("\"", "”", "’", "'")
        ):
            return ""
        return text

    @staticmethod
    def _trim_summary(text: str, *, maximum_words: int) -> str:
        words = text.split()
        if len(words) <= maximum_words:
            return text.strip()

        candidate = " ".join(words[:maximum_words]).strip()
        sentence_ends = [
            match.end()
            for match in re.finditer(r"[.!?](?=\s|$)", candidate)
        ]
        if sentence_ends:
            complete = candidate[: sentence_ends[-1]].strip()
            if len(complete.split()) >= 30:
                return complete
        return candidate.rstrip(" ,;:-") + ("" if candidate.endswith((".", "!", "?")) else "…")

    def _attach_story_image(
        self,
        story: Story,
        image_service: Any,
        result: PoliceCollectionResult,
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
            # A custom or future image service must not prevent Police
            # Intelligence from collecting and processing the story.
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
            or "Untitled police story"
        )

    @staticmethod
    def _default_scraper_factory() -> PoliceScraper:
        return PoliceScraper(
            limit=20,
            headless=True,
        )

    @staticmethod
    def _default_image_service_factory() -> ImageService:
        return ImageService()


__all__ = [
    "PoliceCollectionResult",
    "PoliceCollectionService",
]
