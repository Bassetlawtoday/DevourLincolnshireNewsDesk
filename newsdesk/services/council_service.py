"""Collection, recency, classification and deduplication for Council Intelligence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any

from newsdesk.services.image_service import ImageService
from newsdesk.sources.council_scraper import (
    CouncilSource,
    CouncilSourceHealth,
    CouncilSourceScraper,
    load_council_config,
)
from newsdesk.story import Story
from newsdesk.sources.managed_websites import collect_managed_websites


TOP_PRIORITY = "TOP PRIORITY"
HIGH_LOCAL_IMPORTANCE = "HIGH LOCAL IMPORTANCE"
LOCAL = "LOCAL"
REVIEW = "REVIEW"
PRIORITY_ORDER = {
    TOP_PRIORITY: 0,
    HIGH_LOCAL_IMPORTANCE: 1,
    LOCAL: 2,
    REVIEW: 3,
}


@dataclass(slots=True)
class CouncilCollectionResult:
    stories: list[Story] = field(default_factory=list)
    publish_results: dict[int, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    source_health: dict[str, CouncilSourceHealth] = field(default_factory=dict)
    duplicate_urls_removed: int = 0
    duplicate_headlines_removed: int = 0

    @property
    def collected_count(self) -> int:
        return len(self.stories)

    @property
    def successful(self) -> bool:
        return any(item.successful for item in self.source_health.values())

    def source_health_payload(self) -> dict[str, dict]:
        return {key: asdict(value) for key, value in self.source_health.items()}


class CouncilPriorityClassifier:
    """Apply transparent location-led Council priorities and one category."""

    _CATEGORY_RULES = (
        ("Housing", ("housing", "tenant", "homeless", "landlord", "repairs")),
        ("Planning and Regeneration", ("planning", "regeneration", "development", "brownfield")),
        ("Transport", ("transport", "bus", "rail", "road", "junction", "highway", "cycle")),
        ("Business and Economy", ("business", "economy", "employment", "jobs", "investment")),
        ("Environment", ("environment", "carbon", "climate", "recycling", "park", "green")),
        ("Leisure and Culture", ("museum", "leisure", "culture", "festival", "theatre", "sport")),
        ("Health and Wellbeing", ("health", "wellbeing", "care", "fitness")),
        ("Education and Skills", ("school", "education", "skills", "college", "training")),
        ("Funding", ("funding", "grant", "fund", "award")),
        ("Consultation", ("consultation", "have your say", "survey", "views")),
        ("Governance", ("councillor", "cabinet", "governance", "reorganisation", "constitution")),
        ("Community", ("community", "resident", "families", "volunteer", "charity")),
        ("Council Services", ("council service", "service change", "customer service")),
    )

    def __init__(self, config: dict | None = None):
        self.config = config or load_council_config()
        self.locations = tuple(self.config.get("bassetlaw_locations", ()))
        self.ambiguous = {
            value.casefold() for value in self.config.get("ambiguous_locations", ())
        }
        self.high_terms = tuple(self.config.get("high_local_importance_terms", ()))
        self.outside_terms = tuple(self.config.get("outside_district_terms", ()))
        self._patterns = {
            location: self._boundary_pattern(location) for location in self.locations
        }

    def classify(self, story: Story) -> Story:
        text = " ".join((story.title, story.summary, story.body))
        prominent_text = " ".join((story.title, story.summary))
        locations = self.match_locations(text)
        source_key = str(story.extras.get("source_key", ""))
        if source_key == "bassetlaw_district_council":
            priority = TOP_PRIORITY
            reason = "Official Bassetlaw District Council news"
        elif locations:
            priority = TOP_PRIORITY
            reason = (
                "Direct Bassetlaw mention"
                if locations[0].casefold() == "bassetlaw"
                else f"{locations[0]} location match"
            )
        elif self._contains_any(prominent_text, self.high_terms):
            priority = HIGH_LOCAL_IMPORTANCE
            reason = self._high_importance_reason(prominent_text)
        elif source_key == "nottinghamshire_county_council":
            priority = LOCAL
            reason = "Nottinghamshire-wide information relevant to local readers"
        elif self._contains_any(prominent_text, self.outside_terms):
            priority = REVIEW
            reason = "Outside-district story retained for review"
        elif re.search(r"\b(?:East Midlands|regional|across the region)\b", text, re.I):
            priority = LOCAL
            reason = "Regional announcement with potential local relevance"
        else:
            priority = REVIEW
            reason = "Regional announcement — local relevance unclear"

        story.priority = priority
        story.category = self.category(prominent_text, story.body)
        story.location = ", ".join(locations)
        story.extras.update(
            {
                "priority_reason": reason,
                "matched_locations": locations,
                "priority_order": PRIORITY_ORDER[priority],
            }
        )
        return story

    def match_locations(self, text: str) -> list[str]:
        matches = []
        for location, pattern in self._patterns.items():
            match = pattern.search(text)
            if match is None:
                continue
            if location.casefold() in self.ambiguous and not self._ambiguous_context(
                text, match.start(), match.end()
            ):
                continue
            matches.append(location)
        return matches

    def category(self, text: str, secondary_text: str = "") -> str:
        for candidate_text in (text, secondary_text):
            lowered = candidate_text.casefold()
            for category, terms in self._CATEGORY_RULES:
                if any(re.search(self._word_expression(term), lowered) for term in terms):
                    return category
        return "Other"

    def _high_importance_reason(self, text: str) -> str:
        lowered = text.casefold()
        if "reorganisation" in lowered:
            return "Local government reorganisation affecting Bassetlaw"
        if any(term in lowered for term in ("bus", "rail", "road", "a614", "a1")):
            return "Strategic transport change affecting Bassetlaw"
        if "north nottinghamshire" in lowered or "regional investment" in lowered:
            return "Major investment relevant to North Nottinghamshire"
        return "County-wide service affecting Bassetlaw"

    def _ambiguous_context(self, text: str, start: int, end: int) -> bool:
        context = text[max(0, start - 90): end + 90]
        return bool(
            re.search(
                r"\b(?:Bassetlaw|Nottinghamshire|village|district|near\s+(?:Retford|Worksop))\b",
                context,
                re.I,
            )
        )

    @staticmethod
    def _contains_any(text: str, terms) -> bool:
        lowered = text.casefold()
        return any(
            re.search(CouncilPriorityClassifier._word_expression(term), lowered)
            for term in terms
        )

    @staticmethod
    def _boundary_pattern(value: str) -> re.Pattern:
        escaped = re.escape(value).replace(r"\-", r"[-\s]").replace(r"\ ", r"[\s-]+")
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.I)

    @staticmethod
    def _word_expression(value: str) -> str:
        return rf"(?<![a-z0-9]){re.escape(value.casefold())}(?![a-z0-9])"


class CouncilCollectionService:
    """Collect all enabled Council sources and isolate source failures."""

    def __init__(
        self,
        *,
        config_path=None,
        scraper_factory: Callable[..., Any] | None = None,
        image_service_factory: Callable[[], Any] | None = None,
    ):
        self.config = load_council_config(config_path)
        self.scraper_factory = scraper_factory or CouncilSourceScraper
        self.image_service_factory = image_service_factory or ImageService
        self.classifier = CouncilPriorityClassifier(self.config)

    def collect(self, *, now: datetime | None = None) -> CouncilCollectionResult:
        result = CouncilCollectionResult()
        collected: list[Story] = []
        current = now or datetime.now(timezone.utc)
        for source in self.config["sources"]:
            if not source.enabled:
                continue
            scraper = self.scraper_factory(source, config=self.config)
            try:
                stories, health = scraper.collect(now=current)
            except Exception as error:
                health = CouncilSourceHealth(source.key, source.name)
                health.failures.append(str(error)[:300])
                stories = []
            finally:
                close = getattr(scraper, "close", None)
                if callable(close):
                    close()
            result.source_health[source.key] = health
            if not health.successful:
                result.errors.append(
                    f"{source.name}: {health.failures[0] if health.failures else 'source failed'}"
                )
            collected.extend(stories)

        managed_stories, managed_errors = collect_managed_websites("council")
        collected.extend(managed_stories)
        result.errors.extend(managed_errors)

        deduplicated = self._deduplicate(collected, result)
        for story in deduplicated:
            self.classifier.classify(story)
            source_health = result.source_health.get(story.extras.get("source_key"))
            if source_health and story.extras.get("matched_locations"):
                source_health.direct_bassetlaw_matches += 1

        image_service = self.image_service_factory()
        image_failure_counts: dict[str, int] = {}
        for story in deduplicated:
            if not story.image_url:
                continue
            asset = image_service.get(
                story.image_url,
                fallback_title="Council Intelligence",
            )
            story.attach_image(asset, alt_text=story.image_alt_text)
            if story.image_error:
                source_key = str(story.extras.get("source_key", ""))
                image_failure_counts[source_key] = image_failure_counts.get(source_key, 0) + 1
                health = result.source_health.get(source_key)
                if health is not None:
                    health.failures.append(
                        f"Image for {story.title}: {story.image_error}"[:300]
                    )

        for source_key, count in image_failure_counts.items():
            source_name = result.source_health[source_key].source_name
            result.errors.append(f"{source_name}: {count} image failures")

        result.stories = sorted(
            deduplicated,
            key=lambda story: (
                PRIORITY_ORDER.get(story.priority, 99),
                -self._published_timestamp(story.published),
                story.title.casefold(),
            ),
        )
        return result

    @staticmethod
    def _deduplicate(
        stories: list[Story], result: CouncilCollectionResult
    ) -> list[Story]:
        by_url: dict[str, Story] = {}
        for story in stories:
            canonical = CouncilSourceScraper.canonical_url(story.url)
            if canonical in by_url:
                result.duplicate_urls_removed += 1
                continue
            story.url = canonical
            by_url[canonical] = story

        retained: list[Story] = []
        by_title: dict[str, Story] = {}
        for story in by_url.values():
            title_key = re.sub(r"[^a-z0-9]+", " ", story.title.casefold()).strip()
            existing = by_title.get(title_key)
            if existing is None:
                by_title[title_key] = story
                retained.append(story)
                continue
            if story.extras.get("source_key") == "bassetlaw_district_council":
                retained[retained.index(existing)] = story
                by_title[title_key] = story
            result.duplicate_headlines_removed += 1
        return retained

    @staticmethod
    def _published_timestamp(value: str) -> float:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except (TypeError, ValueError):
            return 0.0


__all__ = [
    "CouncilCollectionResult", "CouncilCollectionService", "CouncilPriorityClassifier",
    "HIGH_LOCAL_IMPORTANCE", "LOCAL", "PRIORITY_ORDER", "REVIEW", "TOP_PRIORITY",
]
