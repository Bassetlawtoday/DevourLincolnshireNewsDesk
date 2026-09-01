"""
BBC Motorsport RSS scraper for SportDesk.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class BBCMotorsportScraper(BaseRssScraper):
    """Collect motorsport stories from the BBC Sport RSS feed."""

    FEED_URL = "https://feeds.bbci.co.uk/sport/motorsport/rss.xml"
    SOURCE_NAME = "BBC Sport - Motorsport"
    CATEGORY = "Motorsport"


__all__ = ["BBCMotorsportScraper"]