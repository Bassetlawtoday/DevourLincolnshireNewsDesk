from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..connectors.structured_html import StructuredHtmlConnector
from ..html_utils import parse_datetime
from ..models import EventRecord


_RANGE_RE = re.compile(r"(\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2})\s*[-–]\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2})", re.I)
_DATE_RE = re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}", re.I)


class TourismCalendarConnector(StructuredHtmlConnector):
    """Reusable tourism/destination calendar connector.

    Designed for Simpleview-style and similar destination pages where event
    title/date are server-rendered but CSS classes differ by destination.
    """

    source_name = "tourism_calendar"

    def __init__(self, url: str, *, source_name: str, area: str | None = None,
                 source_rank: int = 25, **kwargs):
        super().__init__(url, source_name=source_name, source_rank=source_rank, **kwargs)
        self.area = area

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        seen: set[str] = set()

        candidates = soup.select(
            "article, .event-item, .event-listing, .product-listing, .product-list-item, "
            ".listing-item, .card, li"
        )
        for card in candidates:
            heading = card.find(["h2", "h3", "h4"])
            if not heading:
                continue
            title = heading.get_text(" ", strip=True)
            text = card.get_text(" ", strip=True)
            range_match = _RANGE_RE.search(text)
            dates = _DATE_RE.findall(text)
            if not range_match and not dates:
                continue
            link = heading.find("a", href=True) or card.find("a", href=True)
            href = link.get("href") if link else None
            event_url = urljoin(self.url, href) if href else None
            identity = event_url or f"{title}|{dates[0] if dates else ''}"
            if identity in seen:
                continue
            if range_match:
                start, end = parse_datetime(range_match.group(1)), parse_datetime(range_match.group(2))
            else:
                start = parse_datetime(dates[0]) if dates else None
                end = None
            img = card.find("img")
            image = img.get("src") or img.get("data-src") if img else None
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=event_url or identity,
                title=title,
                start=start,
                end=end,
                town=self.area,
                image_url=urljoin(self.url, image) if image else None,
                event_url=event_url,
                ticket_url=event_url,
                source_rank=self.source_rank,
                raw={"summary_text": text},
            ))
            seen.add(identity)
        return out


class VisitNottinghamshireConnector(TourismCalendarConnector):
    def __init__(self, url: str = "https://www.visit-nottinghamshire.co.uk/whats-on", **kwargs):
        super().__init__(url, source_name="Visit Nottinghamshire", area="Nottinghamshire", source_rank=24, **kwargs)
