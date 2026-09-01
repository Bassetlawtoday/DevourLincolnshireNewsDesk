"""
Lincoln United official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class LincolnUnitedScraper(BaseRssScraper):
    """Collect official Lincoln United news."""

    FEED_URL = "https://www.lincolnunited.com/feed/"
    SOURCE_NAME = "Lincoln United"
    CATEGORY = "Football"


__all__ = ["LincolnUnitedScraper"]