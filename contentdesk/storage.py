"""SQLite history and analytical queries for LDRS Content Explorer stories."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "contentdesk" / "contentdesk.sqlite"


def _json_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    try:
        parsed = json.loads(str(value or "[]"))
    except (ValueError, TypeError):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()] if isinstance(parsed, list) else []


class ContentStore:
    def __init__(self, path: Path | str = DATABASE_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_stories (
                    article_id TEXT PRIMARY KEY,
                    content_type TEXT NOT NULL DEFAULT 'Story',
                    title TEXT NOT NULL,
                    slug TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    author_email TEXT NOT NULL DEFAULT '',
                    reviewer_email TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    modified_at TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL,
                    image_url TEXT NOT NULL DEFAULT '',
                    image_caption TEXT NOT NULL DEFAULT '',
                    image_credit TEXT NOT NULL DEFAULT '',
                    categories_json TEXT NOT NULL DEFAULT '[]',
                    authorities_json TEXT NOT NULL DEFAULT '[]',
                    fetched_at TEXT NOT NULL,
                    detail_complete INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_content_created ON content_stories(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_content_author ON content_stories(author COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_content_type ON content_stories(content_type);
                CREATE TABLE IF NOT EXISTS content_sync_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL,
                    discovered INTEGER NOT NULL DEFAULT 0,
                    stored INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def start_run(self, scope: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO content_sync_runs(started_at,scope,status) VALUES(?,?,'running')",
                (now, scope),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, *, discovered: int, stored: int, status: str, message: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE content_sync_runs SET completed_at=?, discovered=?, stored=?, status=?, message=? WHERE run_id=?",
                (datetime.now(timezone.utc).isoformat(), discovered, stored, status, message, run_id),
            )

    def upsert_many(self, stories: Iterable[dict]) -> int:
        count = 0
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            for story in stories:
                values = {
                    "article_id": str(story.get("article_id") or "").strip(),
                    "content_type": str(story.get("content_type") or "Story").strip(),
                    "title": str(story.get("title") or "").strip(),
                    "slug": str(story.get("slug") or "").strip(),
                    "summary": str(story.get("summary") or "").strip(),
                    "body": str(story.get("body") or "").strip(),
                    "author": str(story.get("author") or "").strip(),
                    # Contact addresses are not needed for NewsDesk functions and
                    # are intentionally never persisted (retention policy 1.0).
                    "author_email": "",
                    "reviewer_email": "",
                    "created_at": str(story.get("created_at") or "").strip(),
                    "modified_at": str(story.get("modified_at") or "").strip(),
                    "source_url": str(story.get("source_url") or "").strip(),
                    "image_url": str(story.get("image_url") or "").strip(),
                    "image_caption": str(story.get("image_caption") or "").strip(),
                    "image_credit": str(story.get("image_credit") or "").strip(),
                    "categories_json": json.dumps(story.get("categories") or [], ensure_ascii=False),
                    "authorities_json": json.dumps(story.get("authorities") or [], ensure_ascii=False),
                    "fetched_at": now,
                    "detail_complete": 1 if story.get("detail_complete") else 0,
                }
                if not values["article_id"] or not values["title"] or not values["source_url"]:
                    continue
                connection.execute(
                    """
                    INSERT INTO content_stories(
                        article_id,content_type,title,slug,summary,body,author,author_email,
                        reviewer_email,created_at,modified_at,source_url,image_url,image_caption,
                        image_credit,categories_json,authorities_json,fetched_at,detail_complete
                    ) VALUES(
                        :article_id,:content_type,:title,:slug,:summary,:body,:author,:author_email,
                        :reviewer_email,:created_at,:modified_at,:source_url,:image_url,:image_caption,
                        :image_credit,:categories_json,:authorities_json,:fetched_at,:detail_complete
                    )
                    ON CONFLICT(article_id) DO UPDATE SET
                        content_type=excluded.content_type,title=excluded.title,slug=excluded.slug,
                        summary=CASE WHEN excluded.summary<>'' THEN excluded.summary ELSE content_stories.summary END,
                        body=CASE WHEN excluded.body<>'' THEN excluded.body ELSE content_stories.body END,
                        author=excluded.author,author_email=excluded.author_email,
                        reviewer_email=excluded.reviewer_email,created_at=excluded.created_at,
                        modified_at=excluded.modified_at,source_url=excluded.source_url,
                        image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE content_stories.image_url END,
                        image_caption=CASE WHEN excluded.image_caption<>'' THEN excluded.image_caption ELSE content_stories.image_caption END,
                        image_credit=CASE WHEN excluded.image_credit<>'' THEN excluded.image_credit ELSE content_stories.image_credit END,
                        categories_json=CASE WHEN excluded.categories_json<>'[]' THEN excluded.categories_json ELSE content_stories.categories_json END,
                        authorities_json=CASE WHEN excluded.authorities_json<>'[]' THEN excluded.authorities_json ELSE content_stories.authorities_json END,
                        fetched_at=excluded.fetched_at,
                        detail_complete=MAX(content_stories.detail_complete,excluded.detail_complete)
                    """,
                    values,
                )
                count += 1
        return count

    def get(self, article_id: str):
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM content_stories WHERE article_id=?", (str(article_id),)
            ).fetchone()

    def list_stories(self):
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM content_stories ORDER BY created_at DESC, article_id DESC"
            ).fetchall()

    def summary(self) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count, MAX(fetched_at) AS updated FROM content_stories"
            ).fetchone()
            latest = connection.execute(
                """SELECT scope, discovered, stored, completed_at
                   FROM content_sync_runs WHERE status='success'
                   ORDER BY run_id DESC LIMIT 1"""
            ).fetchone()
        return {
            "count": int(row["count"] or 0),
            "updated": str(row["updated"] or "Never"),
            "latest_scope": str(latest["scope"] or "") if latest else "",
            "latest_discovered": int(latest["discovered"] or 0) if latest else 0,
            "latest_stored": int(latest["stored"] or 0) if latest else 0,
            "latest_completed": str(latest["completed_at"] or "") if latest else "",
        }

    def dimension_counts(self, rows=None) -> dict[str, Counter]:
        source_rows = list(rows) if rows is not None else list(self.list_stories())
        authors: Counter = Counter()
        areas: Counter = Counter()
        categories: Counter = Counter()
        types: Counter = Counter()
        for row in source_rows:
            authors[str(row["author"] or "Unknown").strip() or "Unknown"] += 1
            types[str(row["content_type"] or "Unknown").strip() or "Unknown"] += 1
            for area in _json_list(row["authorities_json"]):
                areas[area] += 1
            row_categories = _json_list(row["categories_json"])
            if row_categories:
                for category in row_categories:
                    categories[category] += 1
            else:
                categories["Not downloaded / uncategorised"] += 1
        return {"Author": authors, "Area": areas, "Category": categories, "Type": types}


def decode_list(value) -> list[str]:
    return _json_list(value)
