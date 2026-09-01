from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from ..html_utils import parse_datetime, parse_jsonld_events
from ..models import EventRecord
from .structured_html import StructuredHtmlConnector


class AcademyMusicGroupConnector(StructuredHtmlConnector):
    """Reusable connector for Academy Music Group / O2 Academy venue event pages."""

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        # Broad card candidates keep this resilient to CSS class changes.
        for card in soup.find_all(["article", "li", "div"]):
            text = card.get_text(" ", strip=True)
            if not text or "Find Tickets" not in text and "More Info" not in text:
                continue
            time_el = card.find("time")
            date_text = time_el.get("datetime") if time_el and time_el.has_attr("datetime") else (time_el.get_text(" ", strip=True) if time_el else None)
            link = card.find("a", href=True)
            heading = card.find(["h2", "h3", "h4"])
            if not heading or not link:
                continue
            title = heading.get_text(" ", strip=True)
            venue = None
            for fragment in card.stripped_strings:
                if "O2 Academy" in fragment or "O2 Institute" in fragment:
                    venue = fragment
                    break
            event = EventRecord(
                source=self.source_name,
                source_event_id=urljoin(self.url, link.get("href")),
                title=title,
                start=parse_datetime(date_text),
                venue=venue,
                event_url=urljoin(self.url, link.get("href")),
                ticket_url=urljoin(self.url, link.get("href")),
                status="sold_out" if "sold out" in text.casefold() else None,
                source_rank=self.source_rank,
            )
            out.append(event)
        # Deduplicate broad DOM matches.
        seen, unique = set(), []
        for event in out:
            key = (event.title.casefold(), event.event_url)
            if key not in seen:
                seen.add(key); unique.append(event)
        if unique:
            return unique
        return super().parse_cards(html)
