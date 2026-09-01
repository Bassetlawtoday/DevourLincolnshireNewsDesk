"""Generic configurable official sports website sources."""

from __future__ import annotations

from pathlib import Path

from newsdesk.sports.websites.generic_website_scraper import (
    GenericWebsiteScraper,
)
from newsdesk.sports.websites.loader import WebsiteSourceLoader
from newsdesk.sports.websites.source import WebsiteSource


def default_website_scrapers(
    config_path: str | Path | None = None,
) -> list[GenericWebsiteScraper]:
    """Create fresh scraper instances for all enabled website sources."""

    loader = WebsiteSourceLoader(config_path)
    return [GenericWebsiteScraper(source) for source in loader.load()]


__all__ = [
    "GenericWebsiteScraper",
    "WebsiteSource",
    "WebsiteSourceLoader",
    "default_website_scrapers",
]
