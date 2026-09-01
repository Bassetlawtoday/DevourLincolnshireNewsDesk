"""
Notts County official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed. This provides a stable source of official club news and can be
extended later with website-specific scraping if required.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class NottsCountyScraper(BaseRssScraper):
    """Collect official Notts County news."""

    FEED_URL = "https://www.nottscountyfc.co.uk/rss/news"
    SOURCE_NAME = "Notts County"
    CATEGORY = "Football"


__all__ = ["NottsCountyScraper"]
