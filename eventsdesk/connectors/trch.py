from __future__ import annotations

from urllib.parse import urljoin
from bs4 import BeautifulSoup

from ..html_utils import parse_datetime
from ..models import EventRecord
from .structured_html import StructuredHtmlConnector


class TRCHConnector(StructuredHtmlConnector):
    """Theatre Royal & Royal Concert Hall Nottingham connector."""

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        for card in soup.find_all(["article", "li", "div"]):
            heading = card.find(["h2", "h3", "h4"])
            link = card.find("a", href=True)
            if not heading or not link:
                continue
            href = link.get("href")
            if not href or "whats-on" not in href and "event" not in href:
                continue
            text = card.get_text(" | ", strip=True)
            times = card.find_all("time")
            start = parse_datetime(times[0].get("datetime") if times and times[0].has_attr("datetime") else (times[0].get_text(" ", strip=True) if times else None))
            venue = None
            room = None
            for fragment in card.stripped_strings:
                if fragment in {"Theatre Royal", "Royal Concert Hall"}:
                    venue = fragment
                elif "Auditorium" in fragment or "Hall" in fragment:
                    room = fragment
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=urljoin(self.url, href),
                title=heading.get_text(" ", strip=True),
                start=start,
                venue=venue,
                room=room,
                event_url=urljoin(self.url, href),
                ticket_url=urljoin(self.url, href),
                source_rank=self.source_rank,
                raw={"card_text": text},
            ))
        seen, unique = set(), []
        for e in out:
            if e.event_url not in seen:
                seen.add(e.event_url); unique.append(e)
        return unique
