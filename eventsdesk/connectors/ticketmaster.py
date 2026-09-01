from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..base import BaseConnector, MissingCredentialError
from ..html_utils import parse_datetime
from ..models import EventRecord


class TicketmasterConnector(BaseConnector):
    source_name = "ticketmaster"
    ROOT = "https://app.ticketmaster.com/discovery/v2/events.json"

    def __init__(self, api_key: str | None, *, country_code: str = "GB", size: int = 200, max_pages: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.country_code = country_code
        self.size = min(max(size, 1), 200)
        self.max_pages = max_pages

    def fetch(self) -> list[EventRecord]:
        if not self.api_key:
            raise MissingCredentialError("Ticketmaster API key is required")
        events: list[EventRecord] = []
        for page in range(self.max_pages):
            params = {
                "apikey": self.api_key,
                "countryCode": self.country_code,
                "locale": "en-gb",
                "size": self.size,
                "page": page,
                "sort": "date,asc",
            }
            payload = self.get(self.ROOT, params=params).json()
            raw_events = (payload.get("_embedded") or {}).get("events") or []
            for raw in raw_events:
                events.append(self._map(raw))
            page_info = payload.get("page") or {}
            total_pages = int(page_info.get("totalPages") or 0)
            if not raw_events or page + 1 >= total_pages:
                break
        return self.normalize(events)

    def _map(self, raw: dict[str, Any]) -> EventRecord:
        dates = raw.get("dates") or {}
        start_data = dates.get("start") or {}
        end_data = dates.get("end") or {}
        start = parse_datetime(start_data.get("dateTime"))
        if start is None and start_data.get("localDate"):
            start = parse_datetime(f"{start_data.get('localDate')} {start_data.get('localTime') or '00:00'}")
        end = parse_datetime(end_data.get("dateTime"))
        if end is None and end_data.get("localDate"):
            end = parse_datetime(f"{end_data.get('localDate')} {end_data.get('localTime') or '00:00'}")
        venue = (((raw.get("_embedded") or {}).get("venues") or [{}])[0])
        address = venue.get("address") or {}
        city = venue.get("city") or {}
        state = venue.get("state") or {}
        location = venue.get("location") or {}
        classifications = raw.get("classifications") or []
        segment = ((classifications[0].get("segment") or {}).get("name") if classifications else None)
        images = raw.get("images") or []
        image = max(images, key=lambda i: int(i.get("width") or 0), default={}).get("url")
        price_ranges = raw.get("priceRanges") or []
        price_text = None
        if price_ranges:
            pr = price_ranges[0]
            cur = pr.get("currency") or ""
            mn, mx = pr.get("min"), pr.get("max")
            price_text = f"{cur} {mn}-{mx}" if mn is not None and mx is not None else None
        return EventRecord(
            source=self.source_name,
            source_event_id=raw.get("id"),
            title=raw.get("name") or "Untitled event",
            start=start,
            end=end,
            venue=venue.get("name"),
            address=address.get("line1"),
            town=city.get("name"),
            county=state.get("name"),
            postcode=venue.get("postalCode"),
            latitude=float(location["latitude"]) if location.get("latitude") else None,
            longitude=float(location["longitude"]) if location.get("longitude") else None,
            category=segment,
            description=raw.get("info") or raw.get("pleaseNote"),
            image_url=image,
            event_url=raw.get("url"),
            ticket_url=raw.get("url"),
            price_text=price_text,
            status=(dates.get("status") or {}).get("code"),
            source_rank=30,
            raw=raw,
        )
