"""
Retford FC official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class RetfordFCScraper(BaseRssScraper):
    """Collect official Retford FC news."""

    FEED_URL = "https://retfordfc.co.uk/feed/"
    SOURCE_NAME = "Retford FC"
    CATEGORY = "Football"


__all__ = ["RetfordFCScraper"]
