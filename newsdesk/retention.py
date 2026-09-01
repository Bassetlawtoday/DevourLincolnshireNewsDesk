"""Central, auditable data-retention controls for NewsDesk Pro."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY_VERSION = "1.1 — 30 August 2026"
POLICY_MARKDOWN = PROJECT_ROOT / "docs" / "NEWSDESK_DATA_RETENTION_POLICY.md"
POLICY_HTML = PROJECT_ROOT / "docs" / "NEWSDESK_DATA_RETENTION_POLICY.html"
AUDIT_PATH = PROJECT_ROOT / "data" / "retention" / "cleanup_audit.jsonl"

RETENTION_SCHEDULE = (
    ("Local Democracy full articles and source images", "90 days unless newsletter-selected"),
    ("Local Democracy listing metadata and analytics", "12 months unless newsletter-selected"),
    ("LDRS author/reviewer email addresses", "Not retained"),
    ("Expired EventsDesk events", "90 days unless newsletter-selected"),
    ("Planning records after conclusion", "12 months"),
    ("Facebook working records", "30 days"),
    ("Unsubmitted Social Desk drafts", "90 days"),
    ("Metricool delivery references", "12 months"),
    ("Temporary source-image cache", "14 days"),
    ("Application logs", "30 days"),
    ("Abandoned newsletter drafts", "Review after 90 days; no automatic editorial deletion"),
    ("Published/selected newsletter copy, provenance and approved images", "Permanent editorial archive"),
)


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None


def _newsletter_protection(root: Path) -> tuple[set[str], set[str], set[str]]:
    content_ids: set[str] = set()
    event_ids: set[str] = set()
    planning_refs: set[str] = set()
    path = root / "data" / "newsletter" / "editions.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return content_ids, event_ids, planning_refs
    editions = payload.get("editions", payload) if isinstance(payload, dict) else payload
    for edition in editions if isinstance(editions, list) else []:
        for item in edition.get("items", []) if isinstance(edition, dict) else []:
            if not isinstance(item, dict):
                continue
            module = str(item.get("module_key") or "").casefold()
            story_id = str(item.get("source_story_id") or "").strip()
            identity = str(item.get("source_identity") or "")
            if module == "content" and story_id:
                content_ids.add(story_id)
            elif module == "events" and story_id:
                event_ids.add(story_id)
            elif module == "planning" and story_id:
                planning_refs.add(story_id.casefold())
            if identity:
                if "content" in identity.casefold():
                    content_ids.add(identity.rsplit(":", 1)[-1])
                if "event" in identity.casefold():
                    event_ids.add(identity.rsplit(":", 1)[-1])
    return content_ids, event_ids, planning_refs


def _content_cleanup(root: Path, now: datetime, protected: set[str], dry_run: bool) -> dict[str, int]:
    result = {"emails_removed": 0, "full_articles_minimised": 0, "metadata_removed": 0}
    path = root / "data" / "contentdesk" / "contentdesk.sqlite"
    if not path.exists():
        return result
    cutoff_full = (now - timedelta(days=90)).isoformat()
    cutoff_metadata = (now - timedelta(days=365)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT article_id,created_at,fetched_at,author_email,reviewer_email,body,image_url,image_caption,image_credit FROM content_stories").fetchall()
        for row in rows:
            article_id = str(row["article_id"])
            stamp = _parse(row["created_at"]) or _parse(row["fetched_at"]) or now
            if row["author_email"] or row["reviewer_email"]:
                result["emails_removed"] += 1
                if not dry_run:
                    connection.execute("UPDATE content_stories SET author_email='', reviewer_email='' WHERE article_id=?", (article_id,))
            if article_id in protected:
                continue
            if stamp.isoformat() < cutoff_metadata:
                result["metadata_removed"] += 1
                if not dry_run:
                    connection.execute("DELETE FROM content_stories WHERE article_id=?", (article_id,))
            elif stamp.isoformat() < cutoff_full and any(row[key] for key in ("body", "image_url", "image_caption", "image_credit")):
                result["full_articles_minimised"] += 1
                if not dry_run:
                    connection.execute("UPDATE content_stories SET body='', image_url='', image_caption='', image_credit='', detail_complete=0 WHERE article_id=?", (article_id,))
        if not dry_run:
            connection.execute("DELETE FROM content_sync_runs WHERE started_at < ?", (cutoff_metadata,))
    return result


def _event_cleanup(root: Path, now: datetime, protected: set[str], dry_run: bool) -> int:
    path = root / "data" / "eventsdesk" / "eventsdesk.sqlite"
    if not path.exists():
        return 0
    cutoff = (now - timedelta(days=90)).isoformat()
    removed = 0
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
        if not columns:
            return 0
        date_columns = [name for name in ("end", "start", "end_at", "end_datetime", "start_at", "start_datetime", "last_seen_at", "last_seen") if name in columns]
        if not date_columns:
            return 0
        expression = "COALESCE(" + ",".join(date_columns) + ",'')"
        rows = connection.execute(f"SELECT id FROM events WHERE {expression} <> '' AND {expression} < ?", (cutoff,)).fetchall()
        targets = [str(row[0]) for row in rows if str(row[0]) not in protected]
        removed = len(targets)
        if targets and not dry_run:
            connection.executemany("DELETE FROM events WHERE id=?", ((value,) for value in targets))
    return removed


def _planning_cleanup(root: Path, now: datetime, protected: set[str], dry_run: bool) -> int:
    path = root / "data" / "newsdesk.db"
    if not path.exists():
        return 0
    removed = 0
    cutoff = now - timedelta(days=365)
    with sqlite3.connect(path) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='planning'").fetchone():
            return 0
        rows = connection.execute("SELECT reference,decision_date,status,decision FROM planning WHERE COALESCE(decision_date,'')<>''").fetchall()
        targets = []
        for reference, decision_date, status, decision in rows:
            stamp = _parse(decision_date)
            concluded = bool(str(decision or "").strip()) or any(word in str(status or "").casefold() for word in ("decided", "approved", "refused", "withdrawn", "closed"))
            if concluded and stamp and stamp < cutoff and str(reference).casefold() not in protected:
                targets.append(str(reference))
        removed = len(targets)
        if targets and not dry_run:
            connection.executemany("DELETE FROM planning WHERE reference=?", ((value,) for value in targets))
    return removed


def _file_cleanup(directory: Path, days: int, now: datetime, dry_run: bool, protected: set[str] | None = None) -> int:
    cutoff = now - timedelta(days=days)
    removed = 0
    protected = {value.casefold() for value in (protected or set())}
    if not directory.is_dir():
        return 0
    for path in directory.iterdir():
        if not path.is_file() or path.name.casefold() in protected:
            continue
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                removed += 1
                if not dry_run:
                    path.unlink()
        except OSError:
            LOGGER.warning("Retention could not inspect %s", path)
    return removed


def _social_cleanup(root: Path, now: datetime, dry_run: bool) -> int:
    path = root / "data" / "social" / "drafts.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0
    drafts = payload.get("drafts", []) if isinstance(payload, dict) else []
    kept = []
    removed = 0
    for draft in drafts if isinstance(drafts, list) else []:
        stamp = _parse(draft.get("updated_at")) if isinstance(draft, dict) else None
        submitted = str(draft.get("status") or "").casefold() == "metricool draft" if isinstance(draft, dict) else False
        cutoff = now - timedelta(days=365 if submitted else 90)
        if stamp and stamp < cutoff:
            removed += 1
        else:
            kept.append(draft)
    if removed and not dry_run:
        payload["drafts"] = kept
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return removed


def apply_retention(project_root: Path | None = None, *, dry_run: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """Apply the published schedule and append a non-content audit record."""
    root = Path(project_root or PROJECT_ROOT)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    content_ids, event_ids, planning_refs = _newsletter_protection(root)
    result: dict[str, Any] = {
        "timestamp": current.isoformat(), "policy_version": POLICY_VERSION, "dry_run": dry_run,
        "protected_content_items": len(content_ids), "protected_event_items": len(event_ids),
    }
    try:
        result.update(_content_cleanup(root, current, content_ids, dry_run))
        result["expired_events_removed"] = _event_cleanup(root, current, event_ids, dry_run)
        result["concluded_planning_removed"] = _planning_cleanup(root, current, planning_refs, dry_run)
        result["old_logs_removed"] = _file_cleanup(root / "logs", 30, current, dry_run)
        result["old_cached_images_removed"] = _file_cleanup(
            root / "cache" / "images", 14, current, dry_run,
            {"newsdesk-image-placeholder.png"},
        )
        result["social_drafts_removed"] = _social_cleanup(root, current, dry_run)
        result["status"] = "passed"
    except Exception as exc:  # retention must never prevent newsroom startup
        LOGGER.exception("Data-retention run failed")
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    if not dry_run:
        audit = root / "data" / "retention" / "cleanup_audit.jsonl"
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return result


def latest_audit(project_root: Path | None = None) -> dict[str, Any]:
    path = Path(project_root or PROJECT_ROOT) / "data" / "retention" / "cleanup_audit.jsonl"
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return json.loads(lines[-1]) if lines else {}
    except (OSError, ValueError, TypeError):
        return {}


def policy_text(project_root: Path | None = None) -> str:
    root = Path(project_root or PROJECT_ROOT)
    try:
        return (root / "docs" / "NEWSDESK_DATA_RETENTION_POLICY.md").read_text(encoding="utf-8")
    except OSError:
        return "NewsDesk Pro Data Retention Policy\n\nThe policy document is not installed."
