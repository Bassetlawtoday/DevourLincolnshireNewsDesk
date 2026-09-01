"""
Mansfield Town official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed. This provides a stable source of official club news and can be
extended later with website-specific scraping if required.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class MansfieldTownScraper(BaseRssScraper):
    """Collect official Mansfield Town news."""

    FEED_URL = "https://www.mansfieldtown.net/rss/news"
    SOURCE_NAME = "Mansfield Town"
    CATEGORY = "Football"


__all__ = ["MansfieldTownScraper"]