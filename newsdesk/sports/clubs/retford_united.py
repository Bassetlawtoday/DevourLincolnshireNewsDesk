"""
Retford United official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class RetfordUnitedScraper(BaseRssScraper):
    """Collect official Retford United news."""

    FEED_URL = "https://www.retfordunited.com/feed/"
    SOURCE_NAME = "Retford United"
    CATEGORY = "Football"


__all__ = ["RetfordUnitedScraper"]