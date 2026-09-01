from __future__ import annotations

from typing import Any

from ..base import BaseConnector, MissingCredentialError
from ..html_utils import parse_datetime
from ..models import EventRecord


class SkiddleConnector(BaseConnector):
    source_name = "skiddle"
    ROOT = "https://www.skiddle.com/api/v1/events/search/"

    def __init__(self, api_key: str | None, *, latitude: float | None = None, longitude: float | None = None, radius_miles: int = 100, limit: int = 100, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.latitude = latitude
        self.longitude = longitude
        self.radius_miles = radius_miles
        self.limit = limit

    def fetch(self) -> list[EventRecord]:
        if not self.api_key:
            raise MissingCredentialError("Skiddle API key is required")
        params: dict[str, Any] = {"api_key": self.api_key, "limit": self.limit}
        if self.latitude is not None and self.longitude is not None:
            params.update({"latitude": self.latitude, "longitude": self.longitude, "radius": self.radius_miles})
        payload = self.get(self.ROOT, params=params).json()
        raw_events = payload.get("results") or payload.get("events") or []
        return self.normalize([self._map(x) for x in raw_events])

    def _map(self, raw: dict[str, Any]) -> EventRecord:
        venue = raw.get("venue") or {}
        start = parse_datetime(raw.get("date") or raw.get("startdate") or raw.get("startDate"))
        if start and raw.get("openingtimes"):
            opening = raw.get("openingtimes") or {}
            doors = opening.get("doorsopen") or opening.get("start")
            if doors:
                maybe = parse_datetime(f"{start.date().isoformat()} {doors}")
                start = maybe or start
        return EventRecord(
            source=self.source_name,
            source_event_id=str(raw.get("id") or raw.get("eventid") or "") or None,
            title=raw.get("eventname") or raw.get("name") or "Untitled event",
            start=start,
            venue=venue.get("name") or raw.get("venue_name"),
            address=venue.get("address"),
            town=venue.get("town") or venue.get("city"),
            postcode=venue.get("postcode"),
            latitude=float(venue["latitude"]) if venue.get("latitude") else None,
            longitude=float(venue["longitude"]) if venue.get("longitude") else None,
            category=raw.get("EventCode") or raw.get("eventcode") or raw.get("genre"),
            description=raw.get("description"),
            image_url=raw.get("largeimageurl") or raw.get("imageurl"),
            event_url=raw.get("link") or raw.get("eventurl"),
            ticket_url=raw.get("link") or raw.get("ticketurl"),
            price_text=raw.get("entryprice") or raw.get("price"),
            source_rank=40,
            raw=raw,
        )
