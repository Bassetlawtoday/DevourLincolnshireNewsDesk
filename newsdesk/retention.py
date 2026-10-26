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
POLICY_VERSION = "1.3 — 26 October 2026"
POLICY_MARKDOWN = PROJECT_ROOT / "docs" / "NEWSDESK_DATA_RETENTION_POLICY.md"
POLICY_HTML = PROJECT_ROOT / "docs" / "NEWSDESK_DATA_RETENTION_POLICY.html"
AUDIT_PATH = PROJECT_ROOT / "data" / "retention" / "cleanup_audit.jsonl"

RETENTION_SCHEDULE = (
    ("Active Council, Police, Sport and Local Democracy module content", "7 days"),
    ("LDRS author/reviewer email addresses", "Not retained"),
    ("Facebook working records", "30 days"),
    ("Social Desk local copies", "7 days; remote Metricool/social posts are unaffected"),
    ("Temporary source-image cache", "14 days"),
    ("Application logs", "30 days"),
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


def _content_cleanup(root: Path, now: datetime, dry_run: bool) -> dict[str, int]:
    result = {"emails_removed": 0, "full_articles_minimised": 0, "metadata_removed": 0}
    path = root / "data" / "contentdesk" / "contentdesk.sqlite"
    if not path.exists():
        return result
    cutoff_full = (now - timedelta(days=7)).isoformat()
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
            if stamp.isoformat() < cutoff_full:
                result["metadata_removed"] += 1
                if not dry_run:
                    connection.execute("DELETE FROM content_stories WHERE article_id=?", (article_id,))
        if not dry_run:
            connection.execute("DELETE FROM content_sync_runs WHERE started_at < ?", (cutoff_full,))
    return result


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
        stamp = _parse(draft.get("created_at")) if isinstance(draft, dict) else None
        cutoff = now - timedelta(days=7)
        if stamp and stamp < cutoff:
            removed += 1
        else:
            kept.append(draft)
    if removed and not dry_run:
        payload["drafts"] = kept
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return removed


def _feed_snapshot_cleanup(root: Path, now: datetime, dry_run: bool) -> int:
    """Remove stories older than seven days from active feed snapshots."""
    removed = 0
    cutoff = now - timedelta(days=7)
    directory = root / "data" / "feed_snapshots"
    for module_key in ("council", "police", "sport"):
        for path in (directory / f"{module_key}.json", directory / f"{module_key}.json.bak"):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            payload = document.get("payload") or {}
            stories = list(payload.get("stories") or [])
            keep_indices = []
            for index, story in enumerate(stories):
                stamp = _parse(story.get("published")) if isinstance(story, dict) else None
                if stamp is None or stamp >= cutoff:
                    keep_indices.append(index)
            removed += len(stories) - len(keep_indices)
            if len(keep_indices) == len(stories) or dry_run:
                continue
            remap = {old: new for new, old in enumerate(keep_indices)}
            payload["stories"] = [stories[index] for index in keep_indices]
            payload["publish_results"] = [
                {**row, "story_index": remap[int(row["story_index"])]}
                for row in payload.get("publish_results") or []
                if int(row.get("story_index", -1)) in remap
            ]
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return removed


def apply_retention(project_root: Path | None = None, *, dry_run: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """Apply the published schedule and append a non-content audit record."""
    root = Path(project_root or PROJECT_ROOT)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result: dict[str, Any] = {
        "timestamp": current.isoformat(), "policy_version": POLICY_VERSION, "dry_run": dry_run,
    }
    try:
        result.update(_content_cleanup(root, current, dry_run))
        result["old_logs_removed"] = _file_cleanup(root / "logs", 30, current, dry_run)
        result["old_cached_images_removed"] = _file_cleanup(
            root / "cache" / "images", 14, current, dry_run,
            {"newsdesk-image-placeholder.png"},
        )
        result["social_drafts_removed"] = _social_cleanup(root, current, dry_run)
        result["feed_snapshot_stories_removed"] = _feed_snapshot_cleanup(root, current, dry_run)
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
