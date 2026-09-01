"""
SJR Worksop official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class SJRWorksopScraper(BaseRssScraper):
    """Collect official SJR Worksop news."""

    FEED_URL = "https://sjrworksopfc.com/feed/"
    SOURCE_NAME = "SJR Worksop"
    CATEGORY = "Football"


__all__ = ["SJRWorksopScraper"]