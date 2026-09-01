"""
Alfreton Town official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class AlfretonTownScraper(BaseRssScraper):
    """Collect official Alfreton Town news."""

    FEED_URL = "https://www.alfretontownfootballclub.com/feed/"
    SOURCE_NAME = "Alfreton Town"
    CATEGORY = "Football"


__all__ = ["AlfretonTownScraper"]