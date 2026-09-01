"""
BBC Rugby League RSS scraper for SportDesk.
"""

from __future__ import annotations

from newsdesk.sports.rss.base_rss_scraper import BaseRssScraper


class BBCRugbyLeagueScraper(BaseRssScraper):
    """Collect rugby league stories from the BBC Sport RSS feed."""

    FEED_URL = "https://feeds.bbci.co.uk/sport/rugby-league/rss.xml"
    SOURCE_NAME = "BBC Sport - Rugby League"
    CATEGORY = "Rugby League"


__all__ = ["BBCRugbyLeagueScraper"]