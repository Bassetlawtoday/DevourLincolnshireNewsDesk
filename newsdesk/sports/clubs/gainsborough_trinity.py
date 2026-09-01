"""
Gainsborough Trinity official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class GainsboroughTrinityScraper(BaseRssScraper):
    """Collect official Gainsborough Trinity news."""

    FEED_URL = "https://www.gainsboroughtrinity.com/feed/"
    SOURCE_NAME = "Gainsborough Trinity"
    CATEGORY = "Football"


__all__ = ["GainsboroughTrinityScraper"]