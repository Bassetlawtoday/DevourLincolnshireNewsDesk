"""
Harworth Colliery official website scraper.

Initial implementation uses the shared RSS framework via the club's official
news feed where available.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class HarworthCollieryScraper(BaseRssScraper):
    """Collect official Harworth Colliery news."""

    FEED_URL = "https://www.harworthcollieryfc.co.uk/feed/"
    SOURCE_NAME = "Harworth Colliery"
    CATEGORY = "Football"


__all__ = ["HarworthCollieryScraper"]