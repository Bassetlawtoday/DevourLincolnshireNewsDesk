"""
BBC Rugby Union RSS scraper for SportDesk.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class BBCRugbyUnionScraper(BaseRssScraper):
    """Collect rugby union stories from the BBC Sport RSS feed."""

    FEED_URL = "https://feeds.bbci.co.uk/sport/rugby-union/rss.xml"
    SOURCE_NAME = "BBC Sport - Rugby Union"
    CATEGORY = "Rugby Union"


__all__ = ["BBCRugbyUnionScraper"]