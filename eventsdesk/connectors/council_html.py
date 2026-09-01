from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..base import BaseConnector
from ..html_utils import parse_datetime, parse_jsonld_events
from ..models import EventRecord


_DATE_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\w*\s*\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2}\b",
    re.I,
)


class CouncilHtmlConnector(BaseConnector):
    """Fallback parser for server-rendered council event calendars.

    Extraction order:
      1. schema.org/Event JSON-LD
      2. semantic event/article/listing containers
      3. conservative anchor/date proximity heuristic

    This connector deliberately avoids browser automation. It is intended as a
    safe fallback after API/XHR discovery has failed.
    """

    source_name = "council_html"

    def __init__(self, url: str, *, source_name: str, area: str | None = None,
                 source_rank: int = 15, max_events: int = 500, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.source_name = source_name
        self.area = area
        self.source_rank = source_rank
        self.max_events = max_events

    def fetch(self) -> list[EventRecord]:
        html = self.get(self.url).text
        events = self.parse_html(html)
        if events:
            return self.normalize(events)
        for candidate in self._discover_event_urls(html):
            try:
                found = self.parse_html(self.get(candidate).text)
                if found:
                    return self.normalize(found)
            except Exception:
                continue
        return []

    def _discover_event_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        scored = []
        seen = set()
        for link in soup.find_all("a", href=True):
            href = urljoin(self.url, str(link.get("href")))
            if href in seen:
                continue
            seen.add(href)
            text = link.get_text(" ", strip=True).casefold()
            path = href.casefold()
            score = 0
            if "what's on" in text or "whats on" in text: score += 8
            if re.search(r"\bevents?\b", text): score += 6
            if "things to do" in text: score += 5
            if "whatson" in path or "whats-on" in path or "what-s-on" in path: score += 5
            if re.search(r"/events?(?:/|$|\?)", path): score += 5
            if "leisure" in path or "culture" in path: score += 2
            if score >= 5:
                scored.append((score, href))
        scored.sort(key=lambda x: (-x[0], len(x[1])))
        return [url for _, url in scored[:5]]

    def parse_html(self, html: str) -> list[EventRecord]:
        structured = parse_jsonld_events(
            html,
            source=self.source_name,
            base_url=self.url,
            source_rank=self.source_rank,
        )
        if structured:
            for event in structured:
                if not event.county and self.area:
                    event.county = self.area
            return structured[: self.max_events]

        soup = BeautifulSoup(html, "html.parser")
        events = self._parse_semantic_cards(soup)
        if not events:
            events = self._parse_labelled_blocks(soup)
        if not events:
            events = self._parse_anchor_date_pairs(soup)
        return events[: self.max_events]

    def _parse_semantic_cards(self, soup: BeautifulSoup) -> list[EventRecord]:
        selectors = (
            "article",
            "li.event", "div.event", "section.event",
            "li.event-item", "div.event-item", "article.event-item",
            "li.listing", "div.listing", "article.listing",
            "li.card", "div.card", "article.card",
        )
        seen_nodes: set[int] = set()
        out: list[EventRecord] = []
        for selector in selectors:
            for node in soup.select(selector):
                if id(node) in seen_nodes:
                    continue
                seen_nodes.add(id(node))
                event = self._event_from_node(node)
                if event:
                    out.append(event)
        return self._unique(out)

    def _event_from_node(self, node: Tag) -> EventRecord | None:
        text = node.get_text(" ", strip=True)
        if not _DATE_RE.search(text) and not node.find("time"):
            return None

        title_el = node.select_one("h1, h2, h3, h4, .title, .event-title, [class*='title']")
        link_el = (title_el.find("a", href=True) if title_el else None) or node.find("a", href=True)
        if title_el:
            title = title_el.get_text(" ", strip=True)
        elif link_el:
            title = link_el.get_text(" ", strip=True)
        else:
            return None
        if len(title) < 3 or len(title) > 240:
            return None

        time_el = node.find("time")
        raw_date = None
        if time_el:
            raw_date = time_el.get("datetime") or time_el.get_text(" ", strip=True)
        if not raw_date:
            match = _DATE_RE.search(text)
            raw_date = match.group(0) if match else None
        start = parse_datetime(raw_date)
        if not start:
            return None

        href = str(link_el.get("href")) if link_el and link_el.get("href") else None
        venue_el = node.select_one(".venue, .location, [class*='venue'], [class*='location']")
        image_el = node.find("img")
        image = None
        if image_el:
            image = image_el.get("src") or image_el.get("data-src")

        return EventRecord(
            source=self.source_name,
            source_event_id=urljoin(self.url, href) if href else None,
            title=title,
            start=start,
            venue=venue_el.get_text(" ", strip=True) if venue_el else None,
            county=self.area,
            event_url=urljoin(self.url, href) if href else None,
            ticket_url=urljoin(self.url, href) if href else None,
            image_url=urljoin(self.url, image) if image else None,
            source_rank=self.source_rank,
            raw={"fallback": "semantic-card"},
        )

    def _parse_labelled_blocks(self, soup: BeautifulSoup) -> list[EventRecord]:
        """Parse council lists that render a heading followed by Date/Time/Cost labels."""
        out: list[EventRecord] = []
        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = heading.get_text(" ", strip=True)
            if len(title) < 4 or len(title) > 180:
                continue
            parent = heading.find_parent(["article", "li", "section", "div"]) or heading.parent
            if not isinstance(parent, Tag):
                continue
            text = parent.get_text(" ", strip=True)
            if "date" not in text.casefold() and not _DATE_RE.search(text):
                continue
            date_match = _DATE_RE.search(text)
            if not date_match:
                continue
            start = parse_datetime(date_match.group(0))
            if not start:
                continue
            link = heading.find("a", href=True) or parent.find("a", href=True)
            href = str(link.get("href")) if link else None
            price = None
            m = re.search(r"\bCost\s*[:\-]?\s*(.+?)(?=\bDate\b|\bTime\b|$)", text, re.I)
            if m:
                price = m.group(1).strip()[:160]
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=urljoin(self.url, href) if href else None,
                title=title, start=start, county=self.area,
                event_url=urljoin(self.url, href) if href else None,
                ticket_url=urljoin(self.url, href) if href else None,
                price_text=price, source_rank=self.source_rank,
                raw={"fallback": "labelled-block"},
            ))
        return self._unique(out)

    def _parse_anchor_date_pairs(self, soup: BeautifulSoup) -> list[EventRecord]:
        out: list[EventRecord] = []
        for link in soup.find_all("a", href=True):
            title = link.get_text(" ", strip=True)
            if len(title) < 4 or len(title) > 180:
                continue
            container = link.find_parent(["li", "article", "div", "section"])
            if not container:
                continue
            text = container.get_text(" ", strip=True)
            match = _DATE_RE.search(text)
            if not match:
                continue
            start = parse_datetime(match.group(0))
            if not start:
                continue
            href = str(link.get("href"))
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=urljoin(self.url, href),
                title=title,
                start=start,
                county=self.area,
                event_url=urljoin(self.url, href),
                ticket_url=urljoin(self.url, href),
                source_rank=self.source_rank,
                raw={"fallback": "anchor-date"},
            ))
        return self._unique(out)

    @staticmethod
    def _unique(events: list[EventRecord]) -> list[EventRecord]:
        seen: set[tuple[str, str, str]] = set()
        out: list[EventRecord] = []
        for event in events:
            key = (
                (event.title or "").casefold(),
                event.start.isoformat() if event.start else "",
                event.event_url or "",
            )
            if key not in seen:
                seen.add(key)
                out.append(event)
        return out
