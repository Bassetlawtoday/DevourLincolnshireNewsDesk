"""Cheap local probes used by System Health; no collector or network access."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

from newsdesk.health.models import HealthItem, HealthStatus


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_ROOT / "data" / "newsdesk.db"
EXPECTED_DOCUMENTS = (
    "02 System Architecture.md", "03 Module Lifecycle.md", "04 Dashboard.md",
    "05 Intelligence Modules.md", "06 Shared Services.md", "07 Collectors.md",
    "08 Publishing.md", "09 Configuration.md", "10 Folder Structure.md",
    "11 Developer Guide.md", "12 Changelog.md", "system_health_centre.md",
)
SECRET_KEY = re.compile(r"(?:token|secret|password|authorization|cookie)", re.I)
SECRET_VALUE = re.compile(r"(?:access_token=|\bBearer\s+|\bEAA(?:B|J)[A-Za-z0-9_-]{8,})", re.I)


def file_metadata(path: Path) -> dict:
    try:
        stat = path.stat()
        return {"location": str(path), "exists": True, "size_bytes": stat.st_size, "latest_write": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}
    except OSError:
        return {"location": str(path), "exists": False, "size_bytes": 0, "latest_write": ""}


def probe_database(now=None, path=None) -> HealthItem:
    checked = now or datetime.now(timezone.utc)
    database_path = Path(path or DATABASE)
    details = file_metadata(database_path)
    if not database_path.exists():
        return HealthItem("database", "NewsDesk database", "Data and Cache", HealthStatus.ATTENTION, "Database file is missing.", details, checked, source="SQLite read-only probe", recommended_action="Start NewsDesk Pro to initialise the database", related_path=str(database_path))
    try:
        connection = sqlite3.connect(f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True)
        row = connection.execute("SELECT COUNT(*) FROM planning").fetchone()
        columns = connection.execute("PRAGMA table_info(planning)").fetchall()
        connection.close()
        details.update({"type": "SQLite", "accessible": True, "planning_rows": int(row[0]), "planning_columns": len(columns), "schema_initialised": bool(columns), "lightweight_query": "Passed"})
        status = HealthStatus.HEALTHY if columns else HealthStatus.ATTENTION
        return HealthItem("database", "NewsDesk database", "Data and Cache", status, f"SQLite accessible; {row[0]} Planning records.", details, checked, last_success=checked, source="SQLite read-only query", recommended_action="No action required" if columns else "Review database initialisation", related_path=str(database_path))
    except (sqlite3.Error, OSError) as error:
        details.update({"accessible": False, "latest_error": str(error)[:240]})
        return HealthItem("database", "NewsDesk database", "Data and Cache", HealthStatus.FAILED, "Database read-only query failed.", details, checked, last_failure=checked, source="SQLite read-only query", recommended_action="Review the database file", related_path=str(database_path))


def _contains_secret(value, path="config"):
    if isinstance(value, dict):
        return any(
            (SECRET_KEY.search(str(key)) and item not in (None, "", [], {}))
            or _contains_secret(item, f"{path}.{key}")
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_secret(item, path) for item in value)
    return isinstance(value, str) and bool(SECRET_VALUE.search(value))


def probe_configuration(now=None, config_dir=None) -> HealthItem:
    checked = now or datetime.now(timezone.utc)
    root = Path(config_dir or PROJECT_ROOT / "config")
    files = sorted(root.glob("*.json"))
    errors, secret_files = [], []
    for path in files:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                errors.append(f"{path.name}: top level must be an object")
            if _contains_secret(value):
                secret_files.append(path.name)
        except (OSError, ValueError) as error:
            errors.append(f"{path.name}: {str(error)[:120]}")
    missing = [name for name in ("dashboard.json", "council.json", "sources.json") if not (root / name).exists()]
    errors.extend(f"{name}: missing" for name in missing)
    status = HealthStatus.FAILED if secret_files else HealthStatus.ATTENTION if errors else HealthStatus.HEALTHY
    summary = f"{len(files)} JSON configuration files checked locally."
    if errors: summary += f" {len(errors)} issue(s)."
    if secret_files: summary += " Secret-like configuration detected."
    return HealthItem("configuration", "Configuration files", "Configuration", status, summary, {"files_checked": [path.name for path in files], "errors": errors[:20], "secret_like_files": secret_files}, checked, last_success=checked if status == HealthStatus.HEALTHY else None, last_failure=checked if status == HealthStatus.FAILED else None, source="Local JSON configuration loaders", recommended_action="No action required" if status == HealthStatus.HEALTHY else "Review the relevant configuration file", related_path=str(root))


def probe_documentation(now=None, docs_dir=None) -> HealthItem:
    checked = now or datetime.now(timezone.utc)
    root = Path(docs_dir or PROJECT_ROOT / "docs")
    present = [name for name in EXPECTED_DOCUMENTS if (root / name).exists()]
    missing = [name for name in EXPECTED_DOCUMENTS if name not in present]
    changelog = root / "12 Changelog.md"
    details = {"expected_files": len(EXPECTED_DOCUMENTS), "present_files": len(present), "missing_files": missing, **file_metadata(changelog)}
    return HealthItem("documentation", "Technical documentation", "Documentation", HealthStatus.ATTENTION if missing else HealthStatus.HEALTHY, f"{len(present)} of {len(EXPECTED_DOCUMENTS)} expected documents are present.", details, checked, last_success=checked if not missing else None, source="Local docs directory", recommended_action="Update missing technical documentation" if missing else "No action required", related_path=str(root))
