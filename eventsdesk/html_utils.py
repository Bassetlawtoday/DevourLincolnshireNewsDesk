from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from .models import EventRecord


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return dateparser.parse(str(value), dayfirst=True, fuzzy=False)
    except Exception:
        return None


def jsonld_objects(html: str) -> Iterable[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.string or tag.get_text(" ", strip=True)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        for obj in stack:
            if isinstance(obj, dict) and "@graph" in obj and isinstance(obj["@graph"], list):
                yield from (x for x in obj["@graph"] if isinstance(x, dict))
            elif isinstance(obj, dict):
                yield obj


def parse_jsonld_events(html: str, *, source: str, base_url: str, source_rank: int = 25) -> list[EventRecord]:
    out: list[EventRecord] = []
    for obj in jsonld_objects(html):
        types = obj.get("@type")
        if isinstance(types, str):
            types = [types]
        if not types or "Event" not in types:
            continue
        location = obj.get("location") or {}
        if isinstance(location, list):
            location = location[0] if location else {}
        address = location.get("address") if isinstance(location, dict) else {}
        if isinstance(address, str):
            address = {"streetAddress": address}
        offers = obj.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        image = obj.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")
        url = obj.get("url")
        out.append(EventRecord(
            source=source,
            source_event_id=str(obj.get("@id") or url or "") or None,
            title=str(obj.get("name") or "Untitled event"),
            start=parse_datetime(obj.get("startDate")),
            end=parse_datetime(obj.get("endDate")),
            venue=location.get("name") if isinstance(location, dict) else None,
            address=address.get("streetAddress") if isinstance(address, dict) else None,
            town=address.get("addressLocality") if isinstance(address, dict) else None,
            county=address.get("addressRegion") if isinstance(address, dict) else None,
            postcode=address.get("postalCode") if isinstance(address, dict) else None,
            category=obj.get("eventType") or obj.get("genre"),
            description=obj.get("description"),
            image_url=urljoin(base_url, image) if image else None,
            event_url=urljoin(base_url, url) if url else None,
            ticket_url=urljoin(base_url, offers.get("url")) if isinstance(offers, dict) and offers.get("url") else None,
            price_text=str(offers.get("price")) if isinstance(offers, dict) and offers.get("price") is not None else None,
            status=obj.get("eventStatus"),
            source_rank=source_rank,
            raw={"jsonld": obj},
        ))
    return out
