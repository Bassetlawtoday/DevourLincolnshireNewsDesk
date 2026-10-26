"""Single-timer scheduling calculations for NewsDesk Pro Home."""

from __future__ import annotations

from datetime import datetime, timedelta
import re


INTERVALS = {
    "Every 15 minutes": timedelta(minutes=15),
    "Every 30 minutes": timedelta(minutes=30),
    "Every 60 minutes": timedelta(minutes=60),
    "Every 2 hours": timedelta(hours=2),
    "Every 12 hours": timedelta(hours=12),
}
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class DashboardScheduler:
    @staticmethod
    def validate_fixed_time(value: str) -> bool:
        return bool(TIME_PATTERN.fullmatch(value.strip()))

    @classmethod
    def next_run(
        cls,
        now: datetime,
        mode: str,
        fixed_times: list[str] | None = None,
        last_run: datetime | None = None,
    ) -> datetime | None:
        if mode == "Off":
            return None
        if mode in INTERVALS:
            anchor = last_run if last_run and last_run <= now else now
            return anchor + INTERVALS[mode]
        if mode != "Custom fixed times":
            return None
        valid = sorted({value.strip() for value in fixed_times or [] if cls.validate_fixed_time(value)})
        for offset in (0, 1):
            day = now.date() + timedelta(days=offset)
            for value in valid:
                hour, minute = (int(part) for part in value.split(":"))
                candidate = now.replace(
                    year=day.year, month=day.month, day=day.day,
                    hour=hour, minute=minute, second=0, microsecond=0,
                )
                if candidate > now:
                    return candidate
        return None

    @staticmethod
    def scheduled_minute_key(value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M")

    @classmethod
    def module_is_stale(
        cls,
        module_key: str,
        now: datetime,
        last_successful: datetime | None,
        policy: dict,
    ) -> bool:
        """Return whether persisted data is due under one module policy."""

        mode = policy.get("mode", "Manual only")
        if mode in {"Off", "Manual only"}:
            return False
        if last_successful is None:
            return True
        local_success = last_successful.astimezone(now.tzinfo)
        interval = INTERVALS.get(mode)
        return bool(interval and now - local_success >= interval)

    @classmethod
    def startup_refresh_required(
        cls,
        module_key: str,
        now: datetime,
        last_successful: datetime | None,
        policy: dict,
        has_current_payload: bool,
    ) -> bool:
        mode = policy.get("mode", "Manual only")
        if mode in {"Off", "Manual only"}:
            return False
        if not has_current_payload:
            return True
        return cls.module_is_stale(module_key, now, last_successful, policy)

    @classmethod
    def next_module_run(
        cls,
        module_key: str,
        now: datetime,
        last_successful: datetime | None,
        policy: dict,
    ) -> datetime | None:
        mode = policy.get("mode", "Manual only")
        if mode in {"Off", "Manual only"}:
            return None
        interval = INTERVALS.get(mode)
        if interval is None:
            return None
        if last_successful is None:
            return now
        candidate = last_successful.astimezone(now.tzinfo) + interval
        return candidate if candidate > now else now

    @classmethod
    def module_next_runs(
        cls,
        now: datetime,
        module_policies: dict[str, dict],
        last_successful: dict[str, datetime | None],
    ) -> dict[str, datetime | None]:
        return {
            key: cls.next_module_run(key, now, last_successful.get(key), policy)
            for key, policy in module_policies.items()
        }

