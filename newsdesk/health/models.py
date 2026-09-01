"""Serializable System Health status, item and snapshot models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    INACTIVE = "INACTIVE"
    ATTENTION = "ATTENTION"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


STATUS_PRECEDENCE = {
    HealthStatus.UNKNOWN: 0,
    HealthStatus.INACTIVE: 0,
    HealthStatus.HEALTHY: 1,
    HealthStatus.ATTENTION: 2,
    HealthStatus.DEGRADED: 3,
    HealthStatus.FAILED: 4,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class HealthItem:
    key: str
    display_name: str
    category: str
    status: HealthStatus
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=utc_now)
    last_success: datetime | None = None
    last_failure: datetime | None = None
    source: str = ""
    recommended_action: str = "No action required"
    related_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        for key in ("checked_at", "last_success", "last_failure"):
            value[key] = iso(getattr(self, key))
        return value


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    started_at: datetime
    completed_at: datetime
    duration: float
    overall_status: HealthStatus
    categories: dict[str, dict[str, int]]
    items: tuple[HealthItem, ...]
    warning_count: int
    failure_count: int
    inactive_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": iso(self.started_at),
            "completed_at": iso(self.completed_at),
            "duration": self.duration,
            "overall_status": self.overall_status.value,
            "categories": self.categories,
            "items": [item.to_dict() for item in self.items],
            "warning_count": self.warning_count,
            "failure_count": self.failure_count,
            "inactive_count": self.inactive_count,
        }


def overall_status(items) -> HealthStatus:
    actionable = [item.status for item in items if item.status != HealthStatus.INACTIVE]
    return max(actionable, key=lambda status: STATUS_PRECEDENCE[status], default=HealthStatus.HEALTHY)
