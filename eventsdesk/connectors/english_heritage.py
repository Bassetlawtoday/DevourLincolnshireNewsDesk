from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..connectors.structured_html import StructuredHtmlConnector
from ..html_utils import parse_datetime
from ..models import EventRecord


_DATE_RANGE = re.compile(
    r"(?P<start>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*\d{1,2}\s+[A-Za-z]{3,9}(?:\s+\d{4})?)"
    r"\s*(?:-|–|to)\s*"
    r"(?P<end>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*\d{1,2}\s+[A-Za-z]{3,9}(?:\s+\d{4})?)",
    re.I,
)
_DATE_ONE = re.compile(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}", re.I)
_TIME = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:-|–|to)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.I)


class EnglishHeritageConnector(StructuredHtmlConnector):
    """Parses English Heritage regional event lists.

    A regional URL is preferred because it yields Midlands-only results and
    avoids crawling the entire national catalogue.
    """

    source_name = "english_heritage"

    def __init__(self, url: str, *, source_name: str = "English Heritage",
                 region: str | None = None, source_rank: int = 18, **kwargs):
        super().__init__(url, source_name=source_name, source_rank=source_rank, **kwargs)
        self.region = region

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        seen: set[str] = set()

        # English Heritage regional pages expose event links in server-rendered
        # lists. Keep matching broad enough to tolerate presentational changes.
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(" ", strip=True)
            if not text or len(text) < 4:
                continue
            container = link.find_parent(["li", "article", "section", "div"])
            if container is None:
                continue
            body = container.get_text(" ", strip=True)
            if not (_DATE_ONE.search(body) or _DATE_RANGE.search(body)):
                continue
            event_url = urljoin(self.url, href)
            if event_url in seen:
                continue

            heading = container.find(["h2", "h3", "h4"])
            title = heading.get_text(" ", strip=True) if heading else text
            range_match = _DATE_RANGE.search(body)
            start = end = None
            if range_match:
                start_text, end_text = range_match.group("start"), range_match.group("end")
                # Carry year from the end date when the first half omits it.
                year_match = re.search(r"\b(20\d{2})\b", end_text)
                if year_match and not re.search(r"\b20\d{2}\b", start_text):
                    start_text = f"{start_text} {year_match.group(1)}"
                start, end = parse_datetime(start_text), parse_datetime(end_text)
            else:
                one = _DATE_ONE.search(body)
                start = parse_datetime(one.group(0)) if one else None

            time_match = _TIME.search(body)
            if start and time_match:
                t = parse_datetime(time_match.group(1))
                if t:
                    start = start.replace(hour=t.hour, minute=t.minute)

            venue = None
            if title in body:
                after = body.split(title, 1)[-1].strip()
                # Venue is often the trailing phrase after date/time. Store only
                # when a short candidate can be inferred safely.
                candidates = [x.strip() for x in re.split(r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?", after, flags=re.I) if x.strip()]
                if candidates and len(candidates[-1]) <= 80:
                    venue = candidates[-1].strip(" -–") or None

            out.append(EventRecord(
                source=self.source_name,
                source_event_id=event_url,
                title=title,
                start=start,
                end=end,
                venue=venue,
                county=self.region,
                event_url=event_url,
                ticket_url=event_url,
                source_rank=self.source_rank,
                raw={"summary_text": body},
            ))
            seen.add(event_url)
        return out
