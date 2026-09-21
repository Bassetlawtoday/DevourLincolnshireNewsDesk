from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from newsdesk.story import Story


ELIGIBLE_MODULES = frozenset({"police", "fire", "sport", "council", "events", "content"})
STATUS_NEW = "new"
STATUS_SOCIAL = "sent_to_social_desk"
STATUS_METRICOOL = "sent_to_metricool"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value):
    """Normalise nested date values supplied by source collectors."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise TypeError(
        f"Object of type {value.__class__.__name__} is not JSON serializable"
    )


def _story_json(story: Story) -> str:
    return json.dumps(
        story.to_dict(), ensure_ascii=False, default=_json_default
    )


def _identity(module_key: str, story: Story) -> str:
    stable = str(story.story_id or story.url or "").strip().casefold().rstrip("/")
    if not stable:
        stable = "|".join(
            " ".join(str(value or "").split()).casefold()
            for value in (story.source, story.title, story.published)
        )
    if not stable.strip("|"):
        raise ValueError("Update requires a story id, URL, or source/title/date identity.")
    return hashlib.sha256(f"{module_key}|{stable}".encode("utf-8")).hexdigest()


@dataclass(slots=True)
class UpdateItem:
    item_id: str
    module_key: str
    title: str
    source: str
    source_url: str
    published: str
    discovered_at: str
    status: str
    social_draft_id: str
    social_sent_at: str
    metricool_id: str
    metricool_sent_at: str
    story: Story


class UpdatesStore:
    def __init__(self, path: Path | str = Path("data") / "updates_desk.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            # sqlite3.Connection.__exit__ commits or rolls back but does not
            # close the handle. Windows therefore keeps temporary .sqlite
            # files locked unless close() is explicit.
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS seen_updates (
                    item_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS update_items (
                    item_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    published TEXT NOT NULL DEFAULT '',
                    discovered_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    social_draft_id TEXT NOT NULL DEFAULT '',
                    social_sent_at TEXT NOT NULL DEFAULT '',
                    metricool_id TEXT NOT NULL DEFAULT '',
                    metricool_sent_at TEXT NOT NULL DEFAULT '',
                    story_json TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_updates_visible
                    ON update_items(deleted, discovered_at DESC);
            """)

    def ingest(self, module_key: str, stories: Iterable[Story]) -> int:
        key = str(module_key or "").strip().casefold()
        if key not in ELIGIBLE_MODULES:
            return 0
        inserted = 0
        with self._connect() as connection:
            for story in stories:
                if not isinstance(story, Story) or not story.title.strip():
                    continue
                try:
                    item_id = _identity(key, story)
                except ValueError:
                    continue
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO seen_updates(item_id,module_key,first_seen_at) VALUES(?,?,?)",
                    (item_id, key, _now()),
                )
                if cursor.rowcount != 1:
                    # Keep an unsent queue entry current when a source edits the
                    # same story. Sent/deleted records remain immutable and the
                    # permanent identity still prevents another transfer.
                    connection.execute(
                        """UPDATE update_items SET title=?,source=?,source_url=?,
                           published=?,story_json=? WHERE item_id=? AND deleted=0
                           AND status=?""",
                        (story.title.strip(), story.source.strip(), story.url.strip(),
                         story.published.strip(), _story_json(story),
                         item_id, STATUS_NEW),
                    )
                    continue
                connection.execute(
                    """INSERT INTO update_items(
                        item_id,module_key,title,source,source_url,published,
                        discovered_at,status,story_json
                    ) VALUES(?,?,?,?,?,?,?,'new',?)""",
                    (item_id, key, story.title.strip(), story.source.strip(),
                     story.url.strip(), story.published.strip(), _now(),
                     _story_json(story)),
                )
                inserted += 1
        return inserted

    def list_items(self, *, status: str = "", module_key: str = "", query: str = "") -> list[UpdateItem]:
        clauses = ["deleted=0"]
        values: list[str] = []
        if status:
            clauses.append("status=?"); values.append(status)
        if module_key:
            clauses.append("module_key=?"); values.append(module_key.casefold())
        if query:
            clauses.append("(title LIKE ? OR source LIKE ?)")
            value = f"%{query.strip()}%"; values.extend((value, value))
        sql = "SELECT * FROM update_items WHERE " + " AND ".join(clauses) + " ORDER BY discovered_at DESC"
        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        return [self._from_row(row) for row in rows]

    def summary(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute("SELECT status,COUNT(*) count FROM update_items WHERE deleted=0 GROUP BY status").fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {"total": sum(counts.values()), "new": counts.get(STATUS_NEW, 0), "social": counts.get(STATUS_SOCIAL, 0), "metricool": counts.get(STATUS_METRICOOL, 0)}

    def mark_social(self, item_id: str, social_draft_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE update_items SET status=?,social_draft_id=?,social_sent_at=? WHERE item_id=? AND deleted=0 AND status=?",
                (STATUS_SOCIAL, social_draft_id, _now(), item_id, STATUS_NEW),
            )
            if cursor.rowcount != 1:
                raise ValueError("This update has already been sent or deleted.")

    def mark_metricool(self, item_id: str, metricool_id: str) -> None:
        if not item_id:
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE update_items SET status=?,metricool_id=?,metricool_sent_at=? WHERE item_id=? AND deleted=0",
                (STATUS_METRICOOL, str(metricool_id or ""), _now(), item_id),
            )

    def reconcile_social_drafts(self, drafts) -> int:
        changed = 0
        for draft in drafts:
            item_id = str(getattr(draft, "origin_updates_id", "") or "").strip()
            delivered = bool(str(getattr(draft, "metricool_id", "") or "").strip() or str(getattr(draft, "status", "")).casefold() == "sent to metricool as draft")
            if item_id and delivered:
                self.mark_metricool(item_id, getattr(draft, "metricool_id", "")); changed += 1
        return changed

    def delete(self, item_id: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE update_items SET deleted=1 WHERE item_id=?", (item_id,))

    def update_story(self, item_id: str, story: Story) -> None:
        """Replace the review snapshot while preserving identity and workflow state."""
        with self._connect() as connection:
            connection.execute(
                """UPDATE update_items SET title=?,source=?,source_url=?,published=?,
                   story_json=? WHERE item_id=? AND deleted=0""",
                (story.title.strip(), story.source.strip(), story.url.strip(),
                 story.published.strip(), _story_json(story),
                 item_id),
            )

    def set_current_as_baseline(self) -> int:
        """Hide the existing unsent backlog while retaining every seen identity."""
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE update_items SET deleted=1 WHERE deleted=0 AND status=?",
                (STATUS_NEW,),
            )
            return int(cursor.rowcount)

    def clear_completed(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("UPDATE update_items SET deleted=1 WHERE deleted=0 AND status=?", (STATUS_METRICOOL,))
            return int(cursor.rowcount)

    @staticmethod
    def _from_row(row) -> UpdateItem:
        return UpdateItem(
            item_id=row["item_id"], module_key=row["module_key"], title=row["title"],
            source=row["source"], source_url=row["source_url"], published=row["published"],
            discovered_at=row["discovered_at"], status=row["status"],
            social_draft_id=row["social_draft_id"], social_sent_at=row["social_sent_at"],
            metricool_id=row["metricool_id"], metricool_sent_at=row["metricool_sent_at"],
            story=Story.from_dict(json.loads(row["story_json"])),
        )
