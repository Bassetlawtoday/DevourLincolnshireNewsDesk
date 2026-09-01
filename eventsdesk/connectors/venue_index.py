from __future__ import annotations

from bs4 import BeautifulSoup
from urllib.parse import urljoin

from ..base import BaseConnector
from ..models import EventRecord
from .structured_html import _start_from_text


class SecondaryVenueIndexConnector(BaseConnector):
    """Discover one venue's events from a stable third-party venue index.

    This is deliberately a discovery fallback. Records receive a lower source
    authority rank than direct venue records and keep the discovery provider in
    ``raw`` so later enrichment can replace them with first-party detail data.
    """

    source_name = "secondary_venue_index"

    def __init__(self, url: str, *, source_name: str, venue_name: str,
                 discovery_provider: str, source_rank: int = 35,
                 area: str | None = None, max_events: int = 500, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.source_name = source_name
        self.venue_name = venue_name
        self.discovery_provider = discovery_provider
        self.source_rank = max(source_rank, 30)
        self.area = area
        self.max_events = max_events

    def fetch(self) -> list[EventRecord]:
        html = self.get(self.url).text
        return self.normalize(self.parse(html)[: self.max_events])

    def parse(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        seen: set[tuple[str, str]] = set()

        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = heading.get_text(" ", strip=True)
            if not title or title.casefold() in {"what's on here", "upcoming events", "events"}:
                continue
            block = heading.find_parent(["article", "li", "section", "div"]) or heading.parent
            text = block.get_text(" ", strip=True) if block else title
            start = _start_from_text(text)
            if not start:
                # Some venue indexes keep the date in a nearby sibling/card.
                parent = block.parent if block else None
                if parent:
                    start = _start_from_text(parent.get_text(" ", strip=True))
            if not start:
                continue
            link = heading.find("a", href=True) or (block.find("a", href=True) if block else None)
            href = urljoin(self.url, str(link.get("href"))) if link and link.get("href") else self.url
            key = (title.casefold(), start.isoformat())
            if key in seen:
                continue
            seen.add(key)
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=href,
                title=title,
                start=start,
                venue=self.venue_name,
                county=self.area,
                event_url=href,
                ticket_url=href,
                source_rank=self.source_rank,
                raw={"discovery_provider": self.discovery_provider, "discovery_fallback": True},
            ))
        return out
