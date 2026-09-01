from __future__ import annotations

import re
from datetime import datetime
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin

from ..base import BaseConnector
from ..html_utils import parse_datetime, parse_jsonld_events
from ..models import EventRecord
from ..event_quality import is_cta_title

_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DAY = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?[,]?"
# Covers 10 Sep 2026, Sat 10 Sep 2026, 18th Jul 2026, Sat 5 Sep-Sat 19 Sep 2026,
# and date ranges where the year appears only on the final date.
_DATE_TOKEN = rf"(?:{_DAY}\s+)?\d{{1,2}}(?:st|nd|rd|th)?\s*{_MONTH}(?:,?\s+20\d{{2}})?"
_DATE_RE = re.compile(rf"\b({_DATE_TOKEN})(?:\s*[-–—]\s*({_DATE_TOKEN}))?", re.I)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_NUMERIC_DATE_RE = re.compile(r"\b([0-3]?\d)[/-]([01]?\d)[/-]((?:20)?\d{2})\b")
_SHORT_RANGE_RE = re.compile(rf"\b(?:{_DAY}\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s*[-–—]\s*(?:{_DAY}\s+)?\d{{1,2}}(?:st|nd|rd|th)?\s*({_MONTH}),?\s+(20\d{{2}})\b", re.I)


def _start_from_text(text: str):
    """Parse the first explicit event date from common UK listing text."""
    text = text or ""
    numeric = _NUMERIC_DATE_RE.search(text)
    if numeric:
        day, month, year = numeric.groups()
        if len(year) == 2:
            year = "20" + year
        return parse_datetime(f"{day}/{month}/{year}")
    short = _SHORT_RANGE_RE.search(text)
    if short:
        return parse_datetime(f"{short.group(1)} {short.group(2)} {short.group(3)}")
    m = _DATE_RE.search(text)
    if not m:
        return None
    first = m.group(1)
    # A range often has the year only on the end date: "Sat 5 Sep-Sat 19 Sep 2026".
    if not _YEAR_RE.search(first):
        tail = m.group(2) or text[m.end(1):]
        ym = _YEAR_RE.search(tail or "")
        if ym:
            first = f"{first} {ym.group(1)}"
    return parse_datetime(first)


def _title_without_leading_date(text: str) -> str:
    text = " ".join((text or "").split())
    short = _SHORT_RANGE_RE.match(text)
    if short:
        text = text[short.end():].strip(" -–—:|")
    else:
        m = _DATE_RE.match(text)
        if m:
            text = text[m.end():].strip(" -–—:|")
    return text.strip()


class StructuredHtmlConnector(BaseConnector):
    """Reusable server-rendered event-listing connector.

    Extraction order:
      1. schema.org/Event JSON-LD
      2. semantic event cards / articles
      3. heading + nearby date patterns
      4. anchors whose visible text contains both date and event title

    The heuristics are intentionally conservative: an item must contain an
    explicit parseable date and a plausible title before it becomes an event.
    """

    source_name = "structured_html"

    def __init__(self, url: str, *, source_name: str, card_selector: str | None = None,
                 source_rank: int = 20, area: str | None = None, max_events: int = 750,
                 default_venue: str | None = None, default_town: str | None = None,
                 default_postcode: str | None = None, enrich_details: bool = True,
                 max_detail_pages: int = 250, venue_filter: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.source_name = source_name
        self.source_rank = source_rank
        self.area = area
        self.card_selector = card_selector
        self.max_events = max_events
        self.default_venue = default_venue
        self.default_town = default_town
        self.default_postcode = default_postcode
        self.enrich_details = enrich_details
        self.max_detail_pages = max_detail_pages
        self.venue_filter = venue_filter

    def fetch(self) -> list[EventRecord]:
        response = self.get(self.url)
        # requests can default to ISO-8859-1 for text/html without an explicit charset.
        # Prefer a detected encoding so curly quotes/dashes survive correctly.
        if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
            response.encoding = response.apparent_encoding or "utf-8"
        html = response.text
        events = parse_jsonld_events(html, source=self.source_name, base_url=self.url, source_rank=self.source_rank)
        if not events:
            events = self.parse_cards(html)
        events = events[: self.max_events]
        for event in events:
            if self.area and not event.county:
                event.county = self.area
            if self.default_venue and not event.venue:
                event.venue = self.default_venue
            if self.default_town and not event.town:
                event.town = self.default_town
            if self.default_postcode and not event.postcode:
                event.postcode = self.default_postcode
        if self.enrich_details:
            self._enrich_detail_pages(events)
        if self.venue_filter:
            needle = self.venue_filter.casefold()
            events = [e for e in events if needle in ((e.venue or "") + " " + str(e.raw.get("listing_text", ""))).casefold()]
        return self.normalize(events)

    def _enrich_detail_pages(self, events: list[EventRecord]) -> None:
        """Enrich discovered listings from their authoritative detail pages.

        Listing discovery remains authoritative: detail-page failures never remove an
        event. Only missing fields are filled, and source-level defaults remain valid.
        """
        seen: set[str] = set()
        fetched = 0
        for event in events:
            url = event.event_url
            if not url or url in seen or fetched >= self.max_detail_pages:
                continue
            if all((event.description, event.image_url, event.category, event.price_text, event.age_restriction)) and event.start and (event.start.hour or event.start.minute):
                continue
            seen.add(url); fetched += 1
            try:
                response = self.get(url)
                if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
                    response.encoding = response.apparent_encoding or "utf-8"
                self._enrich_from_detail_html(event, response.text, url)
            except Exception as exc:
                event.raw.setdefault("detail_enrichment_error", str(exc))

    def _enrich_from_detail_html(self, event: EventRecord, html: str, page_url: str) -> None:
        structured = parse_jsonld_events(html, source=self.source_name, base_url=page_url, source_rank=self.source_rank)
        if structured:
            detail = structured[0]
            for field in ("start","end","venue","room","address","town","county","postcode","latitude","longitude","category","description","image_url","ticket_url","price_text","status","age_restriction"):
                if getattr(event, field) in (None, "") and getattr(detail, field) not in (None, ""):
                    setattr(event, field, getattr(detail, field))
        soup = BeautifulSoup(html, "html.parser")
        if not event.description:
            node = soup.select_one("meta[name='description'],meta[property='og:description']")
            if node and node.get("content"):
                event.description = str(node.get("content")).strip()
            else:
                node = soup.select_one(".description,.event-description,.summary,.intro,[class*='description'],[class*='summary']")
                if node:
                    event.description = node.get_text(" ", strip=True)
        if not event.image_url:
            node = soup.select_one("meta[property='og:image'],meta[name='twitter:image']")
            if node and node.get("content"):
                event.image_url = urljoin(page_url, str(node.get("content")))
        text = soup.get_text(" ", strip=True)
        if not event.price_text:
            m = re.search(r"(?:tickets?\s*)?(?:from\s+)?£\s?\d+(?:[.,]\d{1,2})?(?:\s*[-–]\s*£?\s?\d+(?:[.,]\d{1,2})?)?", text, re.I)
            if m: event.price_text = m.group(0).strip()
        if not event.age_restriction:
            m = re.search(r"\b(?:ages?\s*)?(\d{1,2})\s*\+\b|\b(?:age|ages|aged)\s*(\d{1,2})(?:\s*\+|\s+and\s+over)?", text, re.I)
            if m:
                age = next((g for g in m.groups() if g), None)
                if age: event.age_restriction = age + "+"
        if event.start and event.start.hour == 0 and event.start.minute == 0:
            for tm in soup.find_all("time"):
                raw = tm.get("datetime") or tm.get_text(" ", strip=True)
                parsed = parse_datetime(raw)
                if parsed and (parsed.hour or parsed.minute):
                    event.start = event.start.replace(hour=parsed.hour, minute=parsed.minute, second=parsed.second)
                    break
        event.raw["detail_enriched"] = True

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []

        selectors = []
        if self.card_selector:
            selectors.append(self.card_selector)
        selectors += [
            "article", "li.event", "div.event", "section.event",
            "li.event-item", "div.event-item", "article.event-item",
            "li.event-card", "div.event-card", "article.event-card",
            "li[class*='event']", "article[class*='event']",
            "div[class*='event-card']", "div[class*='listing']",
        ]
        seen_nodes: set[int] = set()
        for selector in selectors:
            for node in soup.select(selector):
                if id(node) in seen_nodes:
                    continue
                seen_nodes.add(id(node))
                event = self._event_from_node(node)
                if event:
                    out.append(event)

        # Many theatre sites use plain headings/links with dates as adjacent text.
        for heading in soup.find_all(["h2", "h3", "h4"]):
            event = self._event_from_heading(heading)
            if event:
                out.append(event)

        # Some list views (e.g. Curve-style) put "DATE TITLE" in a single anchor.
        for link in soup.find_all("a", href=True):
            text = link.get_text(" ", strip=True)
            start = _start_from_text(text)
            if not start:
                continue
            title = _title_without_leading_date(text)
            if not self._plausible_title(title):
                continue
            href = str(link.get("href"))
            out.append(self._record(title, start, href, None, "dated-anchor"))

        return self._unique(out)

    def _event_from_node(self, node: Tag) -> EventRecord | None:
        text = node.get_text(" ", strip=True)
        time_el = node.find("time")
        raw = (time_el.get("datetime") if time_el and time_el.get("datetime") else None)
        start = parse_datetime(raw) if raw else _start_from_text(text)
        if not start:
            return None
        title_el = node.select_one("h1,h2,h3,h4,.title,.event-title,[class*='event-title']")
        link_el = (title_el.find("a", href=True) if title_el else None) or node.find("a", href=True)
        title = title_el.get_text(" ", strip=True) if title_el else (link_el.get_text(" ", strip=True) if link_el else "")
        title = _title_without_leading_date(title)
        if not self._plausible_title(title):
            return None
        href = str(link_el.get("href")) if link_el and link_el.get("href") else None
        venue_el = node.select_one(".venue,.location,[class*='venue'],[class*='location']")
        venue = venue_el.get_text(" ", strip=True) if venue_el else None
        event = self._record(title, start, href, venue, "semantic-card")
        self._enrich_from_node(event, node)
        return event

    def _event_from_heading(self, heading: Tag) -> EventRecord | None:
        title = _title_without_leading_date(heading.get_text(" ", strip=True))
        if not self._plausible_title(title):
            return None
        link = heading.find("a", href=True)
        # Inspect the heading, nearby siblings and several bounded ancestors.
        candidates = [heading.get_text(" ", strip=True)]
        parent = heading.find_parent(["article", "li", "section", "div"])
        node = heading
        for _ in range(4):
            node = node.parent if isinstance(node, Tag) else None
            if not isinstance(node, Tag):
                break
            txt = node.get_text(" ", strip=True)
            if txt and len(txt) <= 5000:
                candidates.append(txt)
        prev = heading.find_previous_sibling()
        if prev:
            candidates.append(prev.get_text(" ", strip=True))
        nxt = heading.find_next_sibling()
        if nxt:
            candidates.append(nxt.get_text(" ", strip=True))
        start = next((d for d in (_start_from_text(x) for x in candidates) if d), None)
        if not start:
            return None
        if not link and parent:
            link = parent.find("a", href=True)
        href = str(link.get("href")) if link and link.get("href") else None
        venue = None
        if parent:
            venue_el = parent.select_one(".venue,.location,[class*='venue'],[class*='location']")
            venue = venue_el.get_text(" ", strip=True) if venue_el else None
        event = self._record(title, start, href, venue, "heading-date")
        if parent:
            self._enrich_from_node(event, parent)
        return event

    def _enrich_from_node(self, event: EventRecord, node: Tag) -> None:
        """Extract optional publication-quality fields without making them mandatory."""
        image = node.find("img")
        if image:
            src = image.get("src") or image.get("data-src") or image.get("data-lazy-src")
            if src:
                event.image_url = urljoin(self.url, str(src))
        desc = node.select_one(".description,.summary,.excerpt,[class*='description'],[class*='summary'],[class*='excerpt']")
        if desc:
            event.description = desc.get_text(" ", strip=True)
        cat = node.select_one(".category,.genre,.tag,[class*='category'],[class*='genre']")
        if cat:
            event.category = cat.get_text(" ", strip=True)
        text = node.get_text(" ", strip=True)
        event.raw.setdefault("listing_text", text[:1200])
        price = re.search(r"(?:from\s+)?£\s?\d+(?:[.,]\d{1,2})?(?:\s*[-–]\s*£?\s?\d+(?:[.,]\d{1,2})?)?", text, re.I)
        if price:
            event.price_text = price.group(0)
        age = re.search(r"\b(?:ages?\s*)?(\d{1,2})\s*\+\b|\b(?:age|ages|aged)\s*(\d{1,2})(?:\s*\+|\s+and\s+over)?", text, re.I)
        if age:
            event.age_restriction = next((g for g in age.groups() if g), None)
            if event.age_restriction:
                event.age_restriction += "+"
        # If the listing exposes an explicit clock time separately, combine it with
        # a date-only start. Avoid inventing a time from unrelated page text.
        if event.start and event.start.hour == 0 and event.start.minute == 0:
            tm = node.find("time")
            raw = tm.get("datetime") if tm and tm.get("datetime") else None
            parsed = parse_datetime(raw) if raw else None
            if parsed and (parsed.hour or parsed.minute):
                event.start = event.start.replace(hour=parsed.hour, minute=parsed.minute, second=parsed.second)

    def _record(self, title: str, start, href: str | None, venue: str | None, mode: str) -> EventRecord:
        absolute = urljoin(self.url, href) if href else None
        return EventRecord(
            source=self.source_name,
            source_event_id=absolute,
            title=title,
            start=start,
            venue=venue,
            county=self.area,
            event_url=absolute,
            ticket_url=absolute,
            source_rank=self.source_rank,
            raw={"fallback": mode},
        )

    @staticmethod
    def _plausible_title(title: str) -> bool:
        if not (3 <= len(title) <= 220):
            return False
        if is_cta_title(title):
            return False
        bad = {"events", "what's on", "whats on"}
        return title.casefold() not in bad

    @staticmethod
    def _unique(events: list[EventRecord]) -> list[EventRecord]:
        seen: set[tuple[str, str, str]] = set()
        out: list[EventRecord] = []
        for event in events:
            key = ((event.title or "").casefold(), event.start.isoformat() if event.start else "", event.event_url or "")
            if key not in seen:
                seen.add(key)
                out.append(event)
        return out


class SelectorCardConnector(StructuredHtmlConnector):
    def __init__(self, url: str, *, source_name: str, card_selector: str, title_selector: str, date_selector: str | None = None,
                 venue_selector: str | None = None, link_selector: str | None = None, image_selector: str | None = None,
                 source_rank: int = 20, **kwargs):
        super().__init__(url, source_name=source_name, source_rank=source_rank, **kwargs)
        self.card_selector = card_selector
        self.title_selector = title_selector
        self.date_selector = date_selector
        self.venue_selector = venue_selector
        self.link_selector = link_selector
        self.image_selector = image_selector

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        for card in soup.select(self.card_selector):
            title_el = card.select_one(self.title_selector)
            if not title_el:
                continue
            date_el = card.select_one(self.date_selector) if self.date_selector else None
            venue_el = card.select_one(self.venue_selector) if self.venue_selector else None
            link_el = card.select_one(self.link_selector) if self.link_selector else card.find("a", href=True)
            image_el = card.select_one(self.image_selector) if self.image_selector else card.find("img")
            href = link_el.get("href") if link_el else None
            image = image_el.get("src") if image_el else None
            raw_date = date_el.get("datetime") if date_el and date_el.has_attr("datetime") else (date_el.get_text(" ", strip=True) if date_el else None)
            start = parse_datetime(raw_date) or _start_from_text(raw_date or "")
            if not start:
                continue
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=urljoin(self.url, href) if href else None,
                title=title_el.get_text(" ", strip=True),
                start=start,
                venue=venue_el.get_text(" ", strip=True) if venue_el else None,
                image_url=urljoin(self.url, image) if image else None,
                event_url=urljoin(self.url, href) if href else None,
                ticket_url=urljoin(self.url, href) if href else None,
                source_rank=self.source_rank,
            ))
        return out

class PagedStructuredHtmlConnector(StructuredHtmlConnector):
    """Structured HTML connector that follows a simple page query parameter.

    Intended for venue/theatre catalogues that expose normal server-rendered
    event cards over page=1..N. Stops when a page yields no new events.
    """
    def __init__(self, url: str, *, source_name: str, page_param: str = "page",
                 start_page: int = 1, max_pages: int = 25, **kwargs):
        super().__init__(url, source_name=source_name, **kwargs)
        self.page_param = page_param
        self.start_page = start_page
        self.max_pages = max_pages

    def _page_url(self, page: int) -> str:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(self.url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query[self.page_param] = str(page)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def fetch(self) -> list[EventRecord]:
        collected: list[EventRecord] = []
        seen: set[tuple[str, str, str]] = set()
        for page in range(self.start_page, self.start_page + self.max_pages):
            page_url = self._page_url(page)
            html = self.get(page_url).text
            events = parse_jsonld_events(html, source=self.source_name, base_url=page_url, source_rank=self.source_rank)
            if not events:
                events = self.parse_cards(html)
            new_count = 0
            for event in events:
                if self.area and not event.county:
                    event.county = self.area
                key = ((event.title or "").casefold(), event.start.isoformat() if event.start else "", event.event_url or "")
                if key in seen:
                    continue
                seen.add(key)
                collected.append(event)
                new_count += 1
                if len(collected) >= self.max_events:
                    return self.normalize(collected[:self.max_events])
            if page > self.start_page and new_count == 0:
                break
        return self.normalize(collected[:self.max_events])
