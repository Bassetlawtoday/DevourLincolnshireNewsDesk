"""Source scraper exports for Devour Lincolnshire NewsDesk.

Imports are resolved lazily so callers can use ``newsdesk.sources`` without
initialising browser, HTTP, or parser dependencies until a scraper is needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from newsdesk.sources.article_scraper import ArticleLink, ArticleScraper
    from newsdesk.sources.base_scraper import (
        BaseScraper,
        ScrapeReport,
        ScrapeResponse,
        ScraperError,
        ScraperParseError,
        ScraperRequestError,
    )
    from newsdesk.sources.fire_scraper import FireScraper
    from newsdesk.sources.police_scraper import PoliceScraper
    from newsdesk.sources.source_collector import (
        SourceCollectionError,
        SourceCollectionReport,
        SourceCollector,
    )
    from newsdesk.sources.source_definition import SourceDefinition, SourceType

__all__ = [
    "ArticleLink",
    "ArticleScraper",
    "BaseScraper",
    "FireScraper",
    "PoliceScraper",
    "ScrapeReport",
    "ScrapeResponse",
    "ScraperError",
    "ScraperParseError",
    "ScraperRequestError",
    "SourceCollectionError",
    "SourceCollectionReport",
    "SourceCollector",
    "SourceDefinition",
    "SourceType",
]


def __getattr__(name: str) -> Any:
    """Resolve public scraper classes only when requested."""

    if name in {"ArticleLink", "ArticleScraper"}:
        from newsdesk.sources.article_scraper import ArticleLink, ArticleScraper

        return {
            "ArticleLink": ArticleLink,
            "ArticleScraper": ArticleScraper,
        }[name]

    if name in {
        "BaseScraper",
        "ScrapeReport",
        "ScrapeResponse",
        "ScraperError",
        "ScraperParseError",
        "ScraperRequestError",
    }:
        from newsdesk.sources.base_scraper import (
            BaseScraper,
            ScrapeReport,
            ScrapeResponse,
            ScraperError,
            ScraperParseError,
            ScraperRequestError,
        )

        return {
            "BaseScraper": BaseScraper,
            "ScrapeReport": ScrapeReport,
            "ScrapeResponse": ScrapeResponse,
            "ScraperError": ScraperError,
            "ScraperParseError": ScraperParseError,
            "ScraperRequestError": ScraperRequestError,
        }[name]

    if name == "FireScraper":
        from newsdesk.sources.fire_scraper import FireScraper

        return FireScraper

    if name == "PoliceScraper":
        from newsdesk.sources.police_scraper import PoliceScraper

        return PoliceScraper

    if name in {
        "SourceCollectionError",
        "SourceCollectionReport",
        "SourceCollector",
    }:
        from newsdesk.sources.source_collector import (
            SourceCollectionError,
            SourceCollectionReport,
            SourceCollector,
        )

        return {
            "SourceCollectionError": SourceCollectionError,
            "SourceCollectionReport": SourceCollectionReport,
            "SourceCollector": SourceCollector,
        }[name]

    if name in {"SourceDefinition", "SourceType"}:
        from newsdesk.sources.source_definition import SourceDefinition, SourceType

        return {
            "SourceDefinition": SourceDefinition,
            "SourceType": SourceType,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Include lazily exported source names in interactive discovery."""

    return sorted(set(globals()) | set(__all__))
