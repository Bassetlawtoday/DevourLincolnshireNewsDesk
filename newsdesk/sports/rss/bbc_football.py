"""
BBC Football RSS scraper for SportDesk.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class BBCFootballScraper(BaseRssScraper):
    """Collect football stories from the BBC Sport RSS feed."""

    FEED_URL = "https://feeds.bbci.co.uk/sport/football/rss.xml"
    SOURCE_NAME = "BBC Sport - Football"
    CATEGORY = "Football"


__all__ = ["BBCFootballScraper"]