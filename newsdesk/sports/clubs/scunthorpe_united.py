"""
Scunthorpe United official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class ScunthorpeUnitedScraper(BaseRssScraper):
    """Collect official Scunthorpe United news."""

    FEED_URL = "https://www.scunthorpe-united.co.uk/feed/"
    SOURCE_NAME = "Scunthorpe United"
    CATEGORY = "Football"


__all__ = ["ScunthorpeUnitedScraper"]