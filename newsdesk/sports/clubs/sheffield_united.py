"""
Sheffield United official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class SheffieldUnitedScraper(BaseRssScraper):
    """Collect official Sheffield United news."""

    FEED_URL = "https://www.sufc.co.uk/rss/news/"
    SOURCE_NAME = "Sheffield United"
    CATEGORY = "Football"


__all__ = ["SheffieldUnitedScraper"]