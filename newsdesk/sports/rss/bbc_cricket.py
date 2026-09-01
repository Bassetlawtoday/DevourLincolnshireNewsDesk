"""
BBC Cricket RSS scraper for SportDesk.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class BBCCricketScraper(BaseRssScraper):
    """Collect cricket stories from the BBC Sport RSS feed."""

    FEED_URL = "https://feeds.bbci.co.uk/sport/cricket/rss.xml"
    SOURCE_NAME = "BBC Sport - Cricket"
    CATEGORY = "Cricket"


__all__ = ["BBCCricketScraper"]