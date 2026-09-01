"""Conservative startup maintenance for logs and temporary image files."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _remove_old_files(
    directory: Path,
    *,
    patterns: tuple[str, ...],
    days: int,
    protected_names: tuple[str, ...] = (),
) -> int:
    """Delete only matching regular files older than the retention boundary."""

    if days < 1 or not directory.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    protected = {name.casefold() for name in protected_names}
    removed = 0
    candidates = {
        path
        for pattern in patterns
        for path in directory.glob(pattern)
        if path.is_file()
    }
    for path in candidates:
        if path.name.casefold() in protected:
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            LOGGER.warning("Could not inspect or remove temporary file %s", path)
    return removed


def run_startup_maintenance(project_root: Path | None = None) -> dict[str, int]:
    """Apply bounded retention without touching newsroom records or config."""

    root = Path(project_root or PROJECT_ROOT)
    results = {
        "old_logs_removed": _remove_old_files(
            root / "logs",
            patterns=("*.log", "*.log.*"),
            days=30,
        ),
        "old_cached_images_removed": _remove_old_files(
            root / "cache" / "images",
            patterns=("*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif", "*.tmp"),
            days=14,
            protected_names=("newsdesk-image-placeholder.png",),
        ),
    }
    LOGGER.info("Startup maintenance complete: %s", results)
    try:
        from newsdesk.retention import apply_retention
        retention = apply_retention(root)
        results["retention_status"] = retention.get("status", "unknown")
    except Exception:
        LOGGER.exception("Central retention maintenance could not run")
        results["retention_status"] = "failed"
    return results
