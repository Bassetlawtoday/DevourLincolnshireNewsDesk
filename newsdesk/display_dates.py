"""Safe, presentation-only UK date formatting for NewsDesk interfaces."""

from __future__ import annotations

from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Final


DATE_UNAVAILABLE: Final[str] = "Date unavailable"


def parse_display_datetime(value: object) -> datetime | None:
    """Parse supported date values without inventing a missing date."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                for pattern in (
                    "%d %B %Y", "%d %b %Y", "%d/%m/%Y",
                    "%H:%M %d/%m/%Y", "%Y-%m-%d",
                ):
                    try:
                        parsed = datetime.strptime(text, pattern)
                        break
                    except ValueError:
                        continue
                else:
                    return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_uk_date(value: object, fallback: str = DATE_UNAVAILABLE) -> str:
    parsed = parse_display_datetime(value)
    return parsed.strftime("%d %B %Y").lstrip("0") if parsed else fallback


def format_uk_date_short(value: object, fallback: str = DATE_UNAVAILABLE) -> str:
    parsed = parse_display_datetime(value)
    return parsed.strftime("%d %b %Y").lstrip("0") if parsed else fallback


def format_uk_datetime(value: object, fallback: str = DATE_UNAVAILABLE) -> str:
    parsed = parse_display_datetime(value)
    return parsed.astimezone().strftime("%d %B %Y • %H:%M").lstrip("0") if parsed else fallback


__all__ = [
    "DATE_UNAVAILABLE", "format_uk_date", "format_uk_date_short",
    "format_uk_datetime", "parse_display_datetime",
]
