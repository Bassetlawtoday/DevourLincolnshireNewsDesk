"""Small data models used by NewsDesk Pro Home."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class DashboardRefreshResult:
    module_key: str
    display_name: str
    count: int = 0
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    success: bool = False
    error_message: str = ""
    previous_count: int | None = None
    change: int | None = None
    updates_today: int = 0
    updates_date: str = ""
    item_keys: list[str] = field(default_factory=list)
    tracking_started_at: str = ""

    @property
    def duration(self) -> float:
        if self.completed_at is None:
            return 0.0
        return max(0.0, (self.completed_at - self.started_at).total_seconds())

    def to_state(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["completed_at"] = (
            self.completed_at.isoformat() if self.completed_at else None
        )
        data["duration"] = self.duration
        return data


@dataclass(frozen=True, slots=True)
class GovernmentAnnouncement:
    publisher: str
    title: str
    published_at: datetime
    canonical_url: str
    description: str = ""
    content_id: str = ""

    def __post_init__(self) -> None:
        value = self.published_at
        if value.tzinfo is None:
            object.__setattr__(self, "published_at", value.replace(tzinfo=timezone.utc))
