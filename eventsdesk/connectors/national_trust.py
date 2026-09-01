from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..connectors.structured_html import StructuredHtmlConnector
from ..html_utils import parse_datetime, parse_jsonld_events
from ..models import EventRecord


_DATE_RE = re.compile(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}", re.I)
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*(?:to|[-–])\s*(\d{1,2}:\d{2})\b", re.I)


class NationalTrustConnector(StructuredHtmlConnector):
    """Reusable National Trust property events parser.

    Expects a property-level /events page. JSON-LD is preferred when present;
    otherwise server-rendered event summary cards are parsed.
    """

    source_name = "national_trust"

    def __init__(self, url: str, *, source_name: str, venue_name: str | None = None,
                 town: str | None = None, county: str | None = None, source_rank: int = 15, **kwargs):
        super().__init__(url, source_name=source_name, source_rank=source_rank, **kwargs)
        self.venue_name = venue_name or source_name
        self.town = town
        self.county = county

    def fetch(self) -> list[EventRecord]:
        urls = [self.url]
        clean = self.url.rstrip("/")
        if not clean.endswith("/events") and not clean.endswith("/whats-on"):
            urls.insert(0, clean + "/events")
        last_error = None
        for url in urls:
            try:
                response = self.get(url)
                html = response.text
                events = parse_jsonld_events(html, source=self.source_name, base_url=url, source_rank=self.source_rank)
                if not events:
                    events = self.parse_cards(html)
                if events:
                    for event in events:
                        if not event.venue: event.venue = self.venue_name
                        if not event.town: event.town = self.town
                        if not event.county: event.county = self.county
                    return self.normalize(events[: self.max_events])
            except Exception as exc:
                last_error = exc
        if last_error and len(urls) == 1:
            raise last_error
        return []

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        seen: set[str] = set()

        for link in soup.select('a[href*="/events/"]'):
            href = link.get("href")
            if not href:
                continue
            event_url = urljoin(self.url, href)
            if event_url in seen:
                continue
            container = link.find_parent(["article", "li", "section", "div"]) or link.parent
            if container is None:
                continue
            title_el = container.find(["h2", "h3", "h4"]) or link
            title = title_el.get_text(" ", strip=True)
            if not title or title.lower() in {"see all events", "check availability"}:
                continue
            text = container.get_text(" ", strip=True)
            dates = _DATE_RE.findall(text)
            times = _TIME_RE.search(text)
            start = parse_datetime(dates[0]) if dates else None
            end = parse_datetime(dates[-1]) if len(dates) > 1 else None
            if start and times:
                try:
                    start = start.replace(hour=int(times.group(1).split(":")[0]), minute=int(times.group(1).split(":")[1]))
                except Exception:
                    pass
            description = None
            p = container.find("p")
            if p:
                description = p.get_text(" ", strip=True)
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=event_url.rsplit("/", 1)[-1].split("?", 1)[0],
                title=title,
                start=start,
                end=end,
                venue=self.venue_name,
                town=self.town,
                county=self.county,
                description=description,
                event_url=event_url,
                ticket_url=event_url,
                source_rank=self.source_rank,
                raw={"summary_text": text},
            ))
            seen.add(event_url)
        if not out:
            return super().parse_cards(html)
        return out
