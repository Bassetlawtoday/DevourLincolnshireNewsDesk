from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit
import re
import html as html_module


def _repair_mojibake(value: str) -> str:
    """Repair common UTF-8 bytes accidentally decoded as Windows-1252/Latin-1."""
    markers = ("â€™", "â€˜", "â€œ", "â€", "â€“", "â€”", "Â", "Ã")
    if not any(marker in value for marker in markers):
        return value
    for encoding in ("cp1252", "latin1"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if sum(repaired.count(m) for m in markers) < sum(value.count(m) for m in markers):
            return repaired
    return value

def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = html_module.unescape(str(value))
    value = _repair_mojibake(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def canonicalize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        p = urlsplit(url.strip())
        scheme = p.scheme.lower() or "https"
        host = p.netloc.lower().removeprefix("www.")
        path = re.sub(r"/{2,}", "/", p.path or "/")
        if path != "/":
            path = path.rstrip("/")
        return urlunsplit((scheme, host, path, "", ""))
    except Exception:
        return url.strip()


def slug_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass(slots=True)
class EventRecord:
    source: str
    source_event_id: Optional[str]
    title: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    venue: Optional[str] = None
    room: Optional[str] = None
    address: Optional[str] = None
    town: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    event_url: Optional[str] = None
    ticket_url: Optional[str] = None
    price_text: Optional[str] = None
    status: Optional[str] = None
    age_restriction: Optional[str] = None
    series_key: Optional[str] = None
    occurrence_key: Optional[str] = None
    source_rank: int = 50
    quality_score: int = 0
    quality_status: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def normalize(self) -> "EventRecord":
        for attr in (
            "source", "source_event_id", "title", "venue", "room", "address", "town",
            "county", "postcode", "category", "description", "image_url", "event_url",
            "ticket_url", "price_text", "status", "age_restriction", "series_key", "occurrence_key", "quality_status",
        ):
            setattr(self, attr, _clean_text(getattr(self, attr)))
        self.event_url = canonicalize_url(self.event_url)
        self.ticket_url = canonicalize_url(self.ticket_url)
        self.image_url = canonicalize_url(self.image_url)
        return self

    @property
    def canonical_key(self) -> str:
        date_part = self.start.date().isoformat() if self.start else ""
        time_part = self.start.strftime("%H:%M") if self.start and self.start.hour + self.start.minute else ""
        identity = "|".join([
            slug_text(self.title),
            date_part,
            time_part,
            slug_text(self.venue),
            slug_text(self.town),
        ])
        return sha1(identity.encode("utf-8")).hexdigest()

    @property
    def source_key(self) -> str:
        if self.source_event_id:
            return f"{self.source}:{self.source_event_id}"
        if self.event_url:
            return f"{self.source}:{self.event_url}"
        return f"{self.source}:{self.canonical_key}"
