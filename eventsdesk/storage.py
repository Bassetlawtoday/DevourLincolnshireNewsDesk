from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from hashlib import sha1
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .dedupe import deduplicate, likely_duplicate
from .models import EventRecord
from .occurrences import OccurrenceExpander


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def event_payload(event: EventRecord) -> dict:
    data = asdict(event)
    data["start"] = iso(event.start)
    data["end"] = iso(event.end)
    return data


def content_hash(event: EventRecord) -> str:
    # Source identity/raw payload are deliberately excluded. This hash represents
    # user-visible event content and drives change detection.
    data = event_payload(event)
    for key in ("source", "source_event_id", "source_rank", "raw"):
        data.pop(key, None)
    return sha1(_json(data).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class HarvestSummary:
    run_id: int
    raw: int
    deduplicated: int
    inserted: int
    changed: int
    unchanged: int
    reactivated: int
    missing: int
    failures: int


class EventStore:
    """SQLite persistence and change tracking for EventsDesk.

    The store keeps one canonical event row plus every source alias that has
    observed it. A successful source run may mark previously-seen source aliases
    as missing; an event is inactive only when all of its source aliases are
    currently missing.
    """

    def __init__(self, path: str | Path = "eventsdesk.sqlite") -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS harvest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                raw_count INTEGER NOT NULL DEFAULT 0,
                deduplicated_count INTEGER NOT NULL DEFAULT 0,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                changed_count INTEGER NOT NULL DEFAULT 0,
                unchanged_count INTEGER NOT NULL DEFAULT 0,
                reactivated_count INTEGER NOT NULL DEFAULT 0,
                missing_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS harvest_sources (
                run_id INTEGER NOT NULL REFERENCES harvest_runs(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                succeeded INTEGER NOT NULL,
                event_count INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                PRIMARY KEY (run_id, source)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_key TEXT NOT NULL,
                title TEXT NOT NULL,
                start TEXT,
                end TEXT,
                venue TEXT,
                room TEXT,
                address TEXT,
                town TEXT,
                county TEXT,
                postcode TEXT,
                latitude REAL,
                longitude REAL,
                category TEXT,
                description TEXT,
                image_url TEXT,
                event_url TEXT,
                ticket_url TEXT,
                price_text TEXT,
                status TEXT,
                age_restriction TEXT,
                series_key TEXT,
                occurrence_key TEXT,
                quality_score INTEGER NOT NULL DEFAULT 0,
                quality_status TEXT,
                lifecycle_state TEXT NOT NULL DEFAULT 'scheduled',
                preferred_source TEXT NOT NULL,
                source_rank INTEGER NOT NULL DEFAULT 50,
                content_hash TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_changed_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_events_key ON events(canonical_key);
            CREATE INDEX IF NOT EXISTS idx_events_start ON events(start);
            CREATE INDEX IF NOT EXISTS idx_events_active ON events(active);

            CREATE TABLE IF NOT EXISTS event_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                source_key TEXT NOT NULL UNIQUE,
                source_event_id TEXT,
                event_url TEXT,
                source_rank INTEGER NOT NULL DEFAULT 50,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                missing_since TEXT,
                raw_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_event_sources_event ON event_sources(event_id);
            CREATE INDEX IF NOT EXISTS idx_event_sources_source ON event_sources(source);

            CREATE TABLE IF NOT EXISTS event_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                run_id INTEGER REFERENCES harvest_runs(id) ON DELETE SET NULL,
                changed_at TEXT NOT NULL,
                change_type TEXT NOT NULL,
                changed_fields_json TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_changes_event ON event_changes(event_id);
            CREATE INDEX IF NOT EXISTS idx_changes_run ON event_changes(run_id);

            CREATE TABLE IF NOT EXISTS connector_health (
                source TEXT PRIMARY KEY,
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_failure_at TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                total_runs INTEGER NOT NULL DEFAULT 0,
                total_failures INTEGER NOT NULL DEFAULT 0,
                last_event_count INTEGER NOT NULL DEFAULT 0,
                last_attempts INTEGER NOT NULL DEFAULT 0,
                last_duration_seconds REAL,
                last_error TEXT
            );
            """
        )
        # Lightweight migrations for databases created by earlier prototype waves.
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(events)").fetchall()}
        for name, ddl in (
            ("series_key", "ALTER TABLE events ADD COLUMN series_key TEXT"),
            ("occurrence_key", "ALTER TABLE events ADD COLUMN occurrence_key TEXT"),
            ("lifecycle_state", "ALTER TABLE events ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'scheduled'"),
            ("quality_score", "ALTER TABLE events ADD COLUMN quality_score INTEGER NOT NULL DEFAULT 0"),
            ("quality_status", "ALTER TABLE events ADD COLUMN quality_status TEXT"),
        ):
            if name not in columns:
                self.connection.execute(ddl)
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_events_series ON events(series_key)")
        self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_occurrence ON events(occurrence_key) WHERE occurrence_key IS NOT NULL")
        self.connection.commit()

    @staticmethod
    def lifecycle_state_for(event: EventRecord, now: datetime, grace_days: int = 1) -> str:
        status = (event.status or "").casefold()
        if "cancelled" in status or "canceled" in status:
            return "cancelled"
        if "postponed" in status:
            return "postponed"
        boundary = event.end or event.start
        if boundary is not None:
            if boundary.tzinfo is None and now.tzinfo is not None:
                boundary = boundary.replace(tzinfo=now.tzinfo)
            elif boundary.tzinfo is not None and now.tzinfo is None:
                now = now.replace(tzinfo=boundary.tzinfo)
            if boundary < now - timedelta(days=grace_days):
                return "expired"
        return "scheduled"

    def _start_run(self, now: datetime) -> int:
        cur = self.connection.execute(
            "INSERT INTO harvest_runs(started_at) VALUES (?)", (iso(now),)
        )
        return int(cur.lastrowid)

    def _event_from_row(self, row: sqlite3.Row) -> EventRecord:
        return EventRecord(
            source=row["preferred_source"],
            source_event_id=None,
            title=row["title"],
            start=parse_dt(row["start"]),
            end=parse_dt(row["end"]),
            venue=row["venue"], room=row["room"], address=row["address"],
            town=row["town"], county=row["county"], postcode=row["postcode"],
            latitude=row["latitude"], longitude=row["longitude"], category=row["category"],
            description=row["description"], image_url=row["image_url"], event_url=row["event_url"],
            ticket_url=row["ticket_url"], price_text=row["price_text"], status=row["status"],
            age_restriction=row["age_restriction"], series_key=row["series_key"], occurrence_key=row["occurrence_key"],
            source_rank=row["source_rank"], quality_score=row["quality_score"], quality_status=row["quality_status"],
        )

    def _find_existing_event(self, event: EventRecord, source_keys: list[str]) -> Optional[sqlite3.Row]:
        if source_keys:
            placeholders = ",".join("?" for _ in source_keys)
            row = self.connection.execute(
                f"""SELECT e.* FROM events e JOIN event_sources s ON s.event_id=e.id
                    WHERE s.source_key IN ({placeholders}) LIMIT 1""",
                source_keys,
            ).fetchone()
            if row:
                return row

        row = self.connection.execute(
            "SELECT * FROM events WHERE canonical_key=? ORDER BY active DESC, last_seen_at DESC LIMIT 1",
            (event.canonical_key,),
        ).fetchone()
        if row:
            return row

        # Canonical keys include time/venue and can legitimately drift. Search a
        # small date window and apply the same fuzzy duplicate logic used in-memory.
        if event.start:
            day = event.start.date().isoformat()
            rows = self.connection.execute(
                "SELECT * FROM events WHERE substr(start,1,10)=? ORDER BY active DESC", (day,)
            ).fetchall()
            for candidate in rows:
                if likely_duplicate(event, self._event_from_row(candidate)):
                    return candidate
        return None

    @staticmethod
    def _changed_fields(before: EventRecord, after: EventRecord) -> list[str]:
        fields = [
            "title", "start", "end", "venue", "room", "address", "town", "county", "postcode",
            "latitude", "longitude", "category", "description", "image_url", "event_url", "ticket_url",
            "price_text", "status", "age_restriction", "series_key", "occurrence_key", "quality_score", "quality_status", "source", "source_rank",
        ]
        return [name for name in fields if getattr(before, name) != getattr(after, name)]

    def _insert_event(self, event: EventRecord, now: datetime, run_id: int) -> int:
        payload = event_payload(event)
        h = content_hash(event)
        cur = self.connection.execute(
            """INSERT INTO events(
                canonical_key,title,start,end,venue,room,address,town,county,postcode,latitude,longitude,
                category,description,image_url,event_url,ticket_url,price_text,status,age_restriction,series_key,occurrence_key,quality_score,quality_status,lifecycle_state,
                preferred_source,source_rank,content_hash,first_seen_at,last_seen_at,last_changed_at,active
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (
                event.canonical_key,event.title,iso(event.start),iso(event.end),event.venue,event.room,event.address,
                event.town,event.county,event.postcode,event.latitude,event.longitude,event.category,event.description,
                event.image_url,event.event_url,event.ticket_url,event.price_text,event.status,event.age_restriction,
                event.series_key,event.occurrence_key,event.quality_score,event.quality_status,self.lifecycle_state_for(event, now),
                event.source,event.source_rank,h,iso(now),iso(now),iso(now),
            ),
        )
        event_id = int(cur.lastrowid)
        self.connection.execute(
            """INSERT INTO event_changes(event_id,run_id,changed_at,change_type,changed_fields_json,before_json,after_json)
               VALUES (?,?,?,?,?,?,?)""",
            (event_id, run_id, iso(now), "created", _json(list(payload.keys())), None, _json(payload)),
        )
        return event_id

    def _update_event(self, event_id: int, before_row: sqlite3.Row, event: EventRecord, now: datetime, run_id: int) -> tuple[str, list[str]]:
        before = self._event_from_row(before_row)
        changed_fields = self._changed_fields(before, event)
        was_inactive = not bool(before_row["active"])
        new_hash = content_hash(event)
        materially_changed = new_hash != before_row["content_hash"]
        change_type = "reactivated" if was_inactive and not materially_changed else "changed" if materially_changed else "unchanged"

        self.connection.execute(
            """UPDATE events SET canonical_key=?,title=?,start=?,end=?,venue=?,room=?,address=?,town=?,county=?,postcode=?,
               latitude=?,longitude=?,category=?,description=?,image_url=?,event_url=?,ticket_url=?,price_text=?,status=?,
               age_restriction=?,series_key=?,occurrence_key=?,quality_score=?,quality_status=?,lifecycle_state=?,preferred_source=?,source_rank=?,content_hash=?,last_seen_at=?,last_changed_at=CASE WHEN ? THEN ? ELSE last_changed_at END,active=1
               WHERE id=?""",
            (
                event.canonical_key,event.title,iso(event.start),iso(event.end),event.venue,event.room,event.address,event.town,
                event.county,event.postcode,event.latitude,event.longitude,event.category,event.description,event.image_url,
                event.event_url,event.ticket_url,event.price_text,event.status,event.age_restriction,event.series_key,event.occurrence_key,event.quality_score,event.quality_status,
                self.lifecycle_state_for(event, now),event.source,event.source_rank,new_hash,iso(now),
                1 if (materially_changed or was_inactive) else 0,iso(now),event_id,
            ),
        )
        if materially_changed or was_inactive:
            self.connection.execute(
                """INSERT INTO event_changes(event_id,run_id,changed_at,change_type,changed_fields_json,before_json,after_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (event_id, run_id, iso(now), change_type, _json(changed_fields), _json(event_payload(before)), _json(event_payload(event))),
            )
        return change_type, changed_fields

    def _upsert_source_alias(self, event_id: int, source_event: EventRecord, now: datetime) -> None:
        source_event.normalize()
        existing = self.connection.execute(
            "SELECT id,event_id FROM event_sources WHERE source_key=?", (source_event.source_key,)
        ).fetchone()
        raw = _json(source_event.raw)
        if existing:
            self.connection.execute(
                """UPDATE event_sources SET event_id=?,source_event_id=?,event_url=?,source_rank=?,last_seen_at=?,missing_since=NULL,raw_json=?
                   WHERE id=?""",
                (event_id,source_event.source_event_id,source_event.event_url,source_event.source_rank,iso(now),raw,existing["id"]),
            )
        else:
            self.connection.execute(
                """INSERT INTO event_sources(event_id,source,source_key,source_event_id,event_url,source_rank,first_seen_at,last_seen_at,raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (event_id,source_event.source,source_event.source_key,source_event.source_event_id,source_event.event_url,
                 source_event.source_rank,iso(now),iso(now),raw),
            )

    def harvest(
        self,
        raw_events: Iterable[EventRecord],
        failures: Iterable[dict] = (),
        successful_sources: Optional[Iterable[str]] = None,
        observed_at: Optional[datetime] = None,
    ) -> HarvestSummary:
        now = observed_at or utcnow()
        raw = [event.normalize() for event in OccurrenceExpander.expand_many(raw_events)]
        failed = list(failures)
        failed_sources = {str(item.get("source")) for item in failed if item.get("source")}
        if successful_sources is None:
            succeeded_sources = {event.source for event in raw} - failed_sources
        else:
            succeeded_sources = set(successful_sources) - failed_sources

        merged = deduplicate(raw)
        assignments: dict[int, list[EventRecord]] = {id(event): [] for event in merged}
        for source_event in raw:
            candidates = [event for event in merged if likely_duplicate(event, source_event)]
            if candidates:
                # Prefer the closest source rank when multiple fuzzy candidates exist.
                best = min(candidates, key=lambda e: abs(e.source_rank - source_event.source_rank))
                assignments[id(best)].append(source_event)

        inserted = changed = unchanged = reactivated = missing = 0
        source_counts: dict[str, int] = {}
        for event in raw:
            source_counts[event.source] = source_counts.get(event.source, 0) + 1

        with self.transaction():
            run_id = self._start_run(now)
            for source in sorted(succeeded_sources):
                self.connection.execute(
                    "INSERT INTO harvest_sources(run_id,source,succeeded,event_count) VALUES (?,?,1,?)",
                    (run_id, source, source_counts.get(source, 0)),
                )
            for failure in failed:
                source = str(failure.get("source") or "unknown")
                self.connection.execute(
                    """INSERT INTO harvest_sources(run_id,source,succeeded,event_count,error) VALUES (?,?,0,0,?)
                       ON CONFLICT(run_id,source) DO UPDATE SET succeeded=0,error=excluded.error""",
                    (run_id, source, str(failure.get("error") or "unknown error")),
                )

            for event in merged:
                source_events = assignments[id(event)] or [event]
                source_keys = [item.source_key for item in source_events]
                existing = self._find_existing_event(event, source_keys)
                if existing is None:
                    event_id = self._insert_event(event, now, run_id)
                    inserted += 1
                else:
                    event_id = int(existing["id"])
                    state, _ = self._update_event(event_id, existing, event, now, run_id)
                    if state == "changed": changed += 1
                    elif state == "reactivated": reactivated += 1
                    else: unchanged += 1
                for source_event in source_events:
                    self._upsert_source_alias(event_id, source_event, now)

            # Missing is evaluated only for sources that completed successfully.
            # A failed source must never make all of its events disappear.
            for source in succeeded_sources:
                rows = self.connection.execute(
                    "SELECT id,event_id,source_key FROM event_sources WHERE source=? AND missing_since IS NULL",
                    (source,),
                ).fetchall()
                seen_keys = {event.source_key for event in raw if event.source == source}
                for row in rows:
                    if row["source_key"] not in seen_keys:
                        self.connection.execute(
                            "UPDATE event_sources SET missing_since=? WHERE id=?", (iso(now), row["id"])
                        )

            # Mark a canonical event inactive only if every alias is missing.
            active_rows = self.connection.execute("SELECT id,active FROM events").fetchall()
            for event_row in active_rows:
                available = self.connection.execute(
                    "SELECT COUNT(*) FROM event_sources WHERE event_id=? AND missing_since IS NULL",
                    (event_row["id"],),
                ).fetchone()[0]
                if available == 0 and event_row["active"]:
                    self.connection.execute(
                        "UPDATE events SET active=0 WHERE id=?", (event_row["id"],)
                    )
                    self.connection.execute(
                        """INSERT INTO event_changes(event_id,run_id,changed_at,change_type,changed_fields_json)
                           VALUES (?,?,?,?,?)""",
                        (event_row["id"],run_id,iso(now),"missing",_json(["active"])),
                    )
                    missing += 1

            # Refresh time-based lifecycle states even when source content itself did not change.
            for row in self.connection.execute("SELECT * FROM events WHERE active=1").fetchall():
                current = self._event_from_row(row)
                state = self.lifecycle_state_for(current, now)
                if row["lifecycle_state"] != state:
                    self.connection.execute("UPDATE events SET lifecycle_state=? WHERE id=?", (state, row["id"]))
                    self.connection.execute(
                        """INSERT INTO event_changes(event_id,run_id,changed_at,change_type,changed_fields_json,before_json,after_json)
                           VALUES (?,?,?,?,?,?,?)""",
                        (row["id"], run_id, iso(now), "lifecycle", _json(["lifecycle_state"]),
                         _json({"lifecycle_state": row["lifecycle_state"]}), _json({"lifecycle_state": state})),
                    )

            self.connection.execute(
                """UPDATE harvest_runs SET finished_at=?,status='completed',raw_count=?,deduplicated_count=?,inserted_count=?,
                   changed_count=?,unchanged_count=?,reactivated_count=?,missing_count=?,failure_count=? WHERE id=?""",
                (iso(now),len(raw),len(merged),inserted,changed,unchanged,reactivated,missing,len(failed),run_id),
            )

        return HarvestSummary(run_id,len(raw),len(merged),inserted,changed,unchanged,reactivated,missing,len(failed))


    def connector_health(self, source: str) -> Optional[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM connector_health WHERE source=?", (source,)).fetchone()

    def connector_health_rows(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            "SELECT * FROM connector_health ORDER BY COALESCE(last_attempt_at,'') DESC, source LIMIT ?", (limit,)
        ))

    def record_connector_health(
        self, source: str, *, succeeded: bool, event_count: int, attempts: int,
        duration_seconds: float, error: Optional[str] = None, observed_at: Optional[datetime] = None
    ) -> None:
        now = observed_at or utcnow()
        existing = self.connector_health(source)
        failures = 0 if succeeded else (int(existing["consecutive_failures"]) + 1 if existing else 1)
        total_runs = (int(existing["total_runs"]) if existing else 0) + 1
        total_failures = (int(existing["total_failures"]) if existing else 0) + (0 if succeeded else 1)
        self.connection.execute(
            """INSERT INTO connector_health(
                source,last_attempt_at,last_success_at,last_failure_at,consecutive_failures,total_runs,total_failures,
                last_event_count,last_attempts,last_duration_seconds,last_error
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source) DO UPDATE SET
                last_attempt_at=excluded.last_attempt_at,
                last_success_at=CASE WHEN excluded.last_success_at IS NOT NULL THEN excluded.last_success_at ELSE connector_health.last_success_at END,
                last_failure_at=CASE WHEN excluded.last_failure_at IS NOT NULL THEN excluded.last_failure_at ELSE connector_health.last_failure_at END,
                consecutive_failures=excluded.consecutive_failures,total_runs=excluded.total_runs,total_failures=excluded.total_failures,
                last_event_count=excluded.last_event_count,last_attempts=excluded.last_attempts,
                last_duration_seconds=excluded.last_duration_seconds,last_error=excluded.last_error
            """,
            (source, iso(now), iso(now) if succeeded else None, None if succeeded else iso(now), failures, total_runs, total_failures,
             event_count, attempts, duration_seconds, None if succeeded else error),
        )
        self.connection.commit()

    def active_events(self, limit: Optional[int] = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM events WHERE active=1 ORDER BY start IS NULL, start, title"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return list(self.connection.execute(sql, params))

    def current_events(self, limit: Optional[int] = None) -> list[sqlite3.Row]:
        """Publication-facing current events; expired/cancelled history stays in SQLite."""
        sql = """SELECT * FROM events WHERE active=1 AND lifecycle_state IN ('scheduled','postponed')
                 ORDER BY start IS NULL, start, title"""
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return list(self.connection.execute(sql, params))

    def upcoming_events(self, limit: Optional[int] = None) -> list[sqlite3.Row]:
        sql = """SELECT * FROM events WHERE active=1 AND lifecycle_state IN ('scheduled','postponed')
                 ORDER BY start IS NULL, start, title"""
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return list(self.connection.execute(sql, params))

    def series_occurrences(self, series_key: str) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            "SELECT * FROM events WHERE series_key=? ORDER BY start IS NULL,start,title", (series_key,)
        ))

    def recent_changes(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            """SELECT c.*,e.title,e.start,e.venue,e.town FROM event_changes c
               JOIN events e ON e.id=c.event_id ORDER BY c.id DESC LIMIT ?""", (limit,)
        ))

    def run_summary(self, run_id: int) -> Optional[sqlite3.Row]:
        return self.connection.execute("SELECT * FROM harvest_runs WHERE id=?", (run_id,)).fetchone()
