"""
Boston United official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class BostonUnitedScraper(BaseRssScraper):
    """Collect official Boston United news."""

    FEED_URL = "https://www.bostonunited.co.uk/feed/"
    SOURCE_NAME = "Boston United"
    CATEGORY = "Football"


__all__ = ["BostonUnitedScraper"]