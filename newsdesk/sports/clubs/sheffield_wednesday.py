"""
Sheffield Wednesday official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class SheffieldWednesdayScraper(BaseRssScraper):
    """Collect official Sheffield Wednesday news."""

    FEED_URL = "https://www.swfc.co.uk/rss/news/"
    SOURCE_NAME = "Sheffield Wednesday"
    CATEGORY = "Football"


__all__ = ["SheffieldWednesdayScraper"]