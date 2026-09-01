"""
Lincoln City official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class LincolnCityScraper(BaseRssScraper):
    """Collect official Lincoln City news."""

    FEED_URL = "https://www.weareimps.com/rss/news"
    SOURCE_NAME = "Lincoln City"
    CATEGORY = "Football"


__all__ = ["LincolnCityScraper"]