"""
Doncaster Rovers official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class DoncasterRoversScraper(BaseRssScraper):
    """Collect official Doncaster Rovers news."""

    FEED_URL = "https://www.doncasterroversfc.co.uk/rss/news"
    SOURCE_NAME = "Doncaster Rovers"
    CATEGORY = "Football"


__all__ = ["DoncasterRoversScraper"]