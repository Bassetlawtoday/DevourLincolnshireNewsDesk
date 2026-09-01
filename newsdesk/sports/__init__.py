"""
Public API for the SportDesk package.
"""

from __future__ import annotations

from newsdesk.sports.sport_scraper import (
    SportScrapeReport,
    SportScraper,
    SportSourceError,
)

from newsdesk.sports.clubs import default_club_scrapers

__all__ = [
    "SportScrapeReport",
    "SportScraper",
    "SportSourceError",
    "default_club_scrapers",
]