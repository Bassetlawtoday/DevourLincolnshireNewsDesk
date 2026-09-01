from __future__ import annotations

import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

from .occurrences import OccurrenceExpander
from .base import MissingCredentialError
from .storage import EventStore, iso, utcnow


@dataclass(frozen=True, slots=True)
class SchedulePolicy:
    interval_minutes: int
    max_retries: int = 2
    backoff_seconds: float = 5.0
    jitter_seconds: float = 1.0
    timeout_seconds: float = 30.0
    group: str = "default"


@dataclass(slots=True)
class ScheduledSource:
    name: str
    connector_factory: Callable[[], object]
    policy: SchedulePolicy


@dataclass(slots=True)
class SourceRunResult:
    source: str
    succeeded: bool
    events: list
    attempts: int
    duration_seconds: float
    error: Optional[str] = None


DEFAULT_POLICIES = {
    "high-volume": SchedulePolicy(30, max_retries=2, backoff_seconds=3, group="aggregators"),
    "venue": SchedulePolicy(120, max_retries=2, backoff_seconds=5, group="venues"),
    "theatre": SchedulePolicy(180, max_retries=2, backoff_seconds=5, group="theatres"),
    "tourism": SchedulePolicy(360, max_retries=2, backoff_seconds=10, group="tourism"),
    "council": SchedulePolicy(720, max_retries=1, backoff_seconds=15, group="councils"),
    "heritage": SchedulePolicy(720, max_retries=1, backoff_seconds=15, group="heritage"),
}


class HarvestScheduler:
    """Runs connector jobs with due-time checks, bounded concurrency and retry/backoff."""

    def __init__(self, store: EventStore, *, max_workers: int = 4, sleep: Callable[[float], None] = time.sleep):
        self.store = store
        self.max_workers = max(1, int(max_workers))
        self.sleep = sleep

    def due(self, source: ScheduledSource, now: Optional[datetime] = None) -> bool:
        now = now or utcnow()
        health = self.store.connector_health(source.name)
        if health is None or not health["last_attempt_at"]:
            return True
        last = datetime.fromisoformat(health["last_attempt_at"])
        return last + timedelta(minutes=source.policy.interval_minutes) <= now

    def _run_one(self, source: ScheduledSource) -> SourceRunResult:
        started = time.monotonic()
        error = None
        for attempt in range(1, source.policy.max_retries + 2):
            try:
                connector = source.connector_factory()
                events = OccurrenceExpander.expand_many(connector.fetch())
                return SourceRunResult(source.name, True, events, attempt, time.monotonic() - started)
            except Exception as exc:
                error = str(exc)
                if isinstance(exc, MissingCredentialError):
                    break
                if attempt <= source.policy.max_retries:
                    delay = source.policy.backoff_seconds * (2 ** (attempt - 1))
                    if source.policy.jitter_seconds:
                        delay += random.random() * source.policy.jitter_seconds
                    self.sleep(delay)
        return SourceRunResult(source.name, False, [], source.policy.max_retries + 1, time.monotonic() - started, error)

    def run_due(self, sources: Iterable[ScheduledSource], *, now: Optional[datetime] = None) -> dict:
        now = now or utcnow()
        due = [s for s in sources if self.due(s, now)]
        if not due:
            return {"due": 0, "succeeded": 0, "failed": 0, "raw": 0, "harvest": None, "sources": []}

        results: list[SourceRunResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_map = {pool.submit(self._run_one, source): source for source in due}
            for future in as_completed(future_map):
                results.append(future.result())

        raw_events = [event for result in results if result.succeeded for event in result.events]
        successful = [result.source for result in results if result.succeeded]
        failures = [{"source": r.source, "error": r.error or "unknown error"} for r in results if not r.succeeded]
        harvest = self.store.harvest(raw_events, failures=failures, successful_sources=successful, observed_at=now)
        for result in results:
            self.store.record_connector_health(
                result.source,
                succeeded=result.succeeded,
                event_count=len(result.events),
                attempts=result.attempts,
                duration_seconds=result.duration_seconds,
                error=result.error,
                observed_at=now,
            )
        return {
            "due": len(due),
            "succeeded": len(successful),
            "failed": len(failures),
            "raw": len(raw_events),
            "harvest": asdict(harvest),
            "sources": [asdict(r) | {"events": len(r.events)} for r in results],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="EventsDesk scheduler health/status")
    parser.add_argument("--database", default="eventsdesk.sqlite")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    with EventStore(args.database) as store:
        rows = [dict(r) for r in store.connector_health_rows(args.limit)]
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
