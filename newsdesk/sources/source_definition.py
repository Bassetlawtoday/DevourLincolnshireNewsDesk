"""
newsdesk.sources.source_definition

Shared source definitions for NewsDesk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    HTML = "html"
    RSS = "rss"
    JSON = "json"
    API = "api"


@dataclass(slots=True)
class SourceDefinition:
    """
    Immutable definition describing a news source.

    This class deliberately contains configuration only. Scrapers,
    StoryEngine, BaseScraper, SourceLoader and SourceRegistry remain the
    source of truth for execution and publishing.
    """

    name: str
    url: str

    scraper: str

    enabled: bool = True

    category: str = ""

    organisation: str = ""

    source_type: SourceType = SourceType.HTML

    priority: int = 100

    request_delay: float = 0.0

    timeout: float = 30.0

    tags: list[str] = field(default_factory=list)

    headers: dict[str, str] = field(default_factory=dict)

    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.url = self.url.strip()
        self.scraper = self.scraper.strip()

        if not self.name:
            raise ValueError("Source name cannot be empty.")

        if not self.url:
            raise ValueError("Source URL cannot be empty.")

        if not self.scraper:
            raise ValueError("Scraper cannot be empty.")

        if self.timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        if self.request_delay < 0:
            raise ValueError("Request delay cannot be negative.")

    @property
    def is_html(self) -> bool:
        return self.source_type is SourceType.HTML

    @property
    def is_rss(self) -> bool:
        return self.source_type is SourceType.RSS

    @property
    def is_api(self) -> bool:
        return self.source_type is SourceType.API

    def as_loader_kwargs(self) -> dict[str, Any]:
        """
        Convenience helper for SourceLoader/SourceRegistry.
        """
        return {
            "source_name": self.name,
            "source_url": self.url,
            "timeout": self.timeout,
            "request_delay": self.request_delay,
            "extra_headers": dict(self.headers),
        }
