"""Assemble one honest, local-only NewsDesk Pro health snapshot."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from time import perf_counter

from newsdesk.dashboard.planning_cache import PlanningResultCache, SCHEMA_VERSION as PLANNING_SCHEMA_VERSION
from newsdesk.dashboard.registry import HEAVY_MODULE_KEYS, MODULE_DEFINITIONS
from newsdesk.dashboard.result_repository import DashboardResultRepository
from newsdesk.dashboard.scheduler import DashboardScheduler
from newsdesk.dashboard.state_store import DashboardStateStore
from newsdesk.image_preview_cache import IMAGE_PREVIEW_CACHE
from newsdesk.theme import VERSION as APPLICATION_VERSION

from .collectors import file_metadata, probe_configuration, probe_database, probe_documentation
from .models import HealthItem, HealthSnapshot, HealthStatus, overall_status
from .state import HealthStateStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SECRET_PATTERN = re.compile(
    r"(?:(?:access[_-]?token|app[_-]?secret|authorization)"
    r"(?:\s*[:=]\s*[^\s,;\"']+)?|\bBearer\s+[^\s,;\"']+|"
    r"\bEAA(?:B|J)[A-Za-z0-9_-]{8,})",
    re.I,
)
CATEGORIES = ("Modules", "Scheduler", "Data and Cache", "Providers", "Configuration", "Documentation", "Platform")


def _parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


class SystemHealthService:
    """Reads existing operational boundaries without running collection."""

    def __init__(
        self, *, dashboard_state=None, repository=None, planning_cache=None,
        coordinator=None, image_cache=None, health_state=None,
        runtime=None,
    ):
        self.dashboard_state = dashboard_state or DashboardStateStore()
        self.repository = repository or DashboardResultRepository()
        self.planning_cache = planning_cache or PlanningResultCache()
        self.coordinator = coordinator
        self.image_cache = image_cache or IMAGE_PREVIEW_CACHE
        self.health_state = health_state or HealthStateStore()
        self.runtime = runtime

    def snapshot(self, *, now=None, persist=True) -> HealthSnapshot:
        started_at = now or datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        started = perf_counter()
        self.health_state.load()
        state = self.dashboard_state.load()
        items = [self._application_item(started_at)]
        items.extend(self._module_items(state, started_at))
        items.extend(self._scheduler_items(state, started_at))
        items.extend(self._data_items(started_at))
        items.extend((probe_configuration(started_at), probe_database(started_at), probe_documentation(started_at)))
        if self.health_state.corrupt:
            items.append(HealthItem("health_state", "System Health history", "Data and Cache", HealthStatus.ATTENTION, "Health history is unreadable; the original file was preserved.", {"location": str(self.health_state.path)}, started_at, source="HealthStateStore", recommended_action="Review the Health state file", related_path=str(self.health_state.path)))
        completed = datetime.now(timezone.utc)
        statuses = Counter(item.status for item in items)
        categories = {}
        for category in CATEGORIES:
            category_items = [item for item in items if item.category == category]
            if category_items:
                category_counts = Counter(item.status.value for item in category_items)
                categories[category] = {"total": len(category_items), **dict(category_counts)}
        snapshot = HealthSnapshot(
            started_at, completed, perf_counter() - started,
            overall_status(items), categories, tuple(items),
            statuses[HealthStatus.ATTENTION] + statuses[HealthStatus.DEGRADED],
            statuses[HealthStatus.FAILED], statuses[HealthStatus.INACTIVE],
        )
        if persist and not self.health_state.corrupt:
            self.health_state.record(snapshot)
        return snapshot

    def performance_summary(self) -> str:
        """Return the latest module refresh and window-open timings."""

        state = self.dashboard_state.load()
        module_state = state.get("modules") or {}
        lines = ["NewsDesk Pro performance summary"]
        for definition in MODULE_DEFINITIONS:
            saved = module_state.get(definition.key) or {}
            refresh = saved.get("last_duration")
            window_open = saved.get("last_window_open_seconds")
            count = saved.get("latest_successful_count")
            lines.append(
                f"{definition.display_name}: refresh "
                f"{float(refresh):.2f}s" if isinstance(refresh, (int, float)) else
                f"{definition.display_name}: refresh not recorded"
            )
            lines[-1] += (
                f"; open {float(window_open):.3f}s"
                if isinstance(window_open, (int, float))
                else "; open not recorded"
            )
            lines[-1] += f"; items {count if count is not None else 'unknown'}"
        return "\n".join(lines)

    def filter_items(self, snapshot, *, search="", filter_name="All"):
        query = search.strip().casefold()
        output = []
        for item in snapshot.items:
            if query and query not in f"{item.display_name} {item.summary} {item.category}".casefold():
                continue
            if filter_name == "Failures" and item.status != HealthStatus.FAILED: continue
            if filter_name == "Warnings" and item.status not in {HealthStatus.ATTENTION, HealthStatus.DEGRADED}: continue
            if filter_name == "Inactive" and item.status != HealthStatus.INACTIVE: continue
            if filter_name not in {"All", "Failures", "Warnings", "Inactive"} and item.category != filter_name: continue
            output.append(item)
        return output

    def copy_summary(self, snapshot) -> str:
        affected = [f"- {item.status.value}: {item.display_name} — {item.summary}" for item in snapshot.items if item.status in {HealthStatus.FAILED, HealthStatus.DEGRADED, HealthStatus.ATTENTION}]
        text = "\n".join((
            "NewsDesk Pro System Health",
            f"Overall: {snapshot.overall_status.value}",
            f"Checked: {snapshot.completed_at.astimezone().isoformat(timespec='seconds')}",
            f"Warnings: {snapshot.warning_count}  Failures: {snapshot.failure_count}  Inactive: {snapshot.inactive_count}",
            *(affected or ["- No actionable health items"]),
        ))
        return self.redact(text)

    def export_report(self, snapshot, directory=None) -> Path:
        folder = Path(directory or PROJECT_ROOT / "exports" / "health")
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = snapshot.completed_at.astimezone().strftime("%Y-%m-%d_%H%M%S")
        path = folder / f"newsdesk_health_{timestamp}.md"
        git = self.git_information()
        latest_diagnostic = (self.health_state.load().get("diagnostics") or [None])[-1]
        lines = [
            "# NewsDesk Pro System Health Report", "",
            f"Generated: {snapshot.completed_at.astimezone().isoformat(timespec='seconds')}",
            f"Application version: {APPLICATION_VERSION}",
            f"Git: {git}", "", self.copy_summary(snapshot), "",
        ]
        sections = (
            ("Module summary", {"Modules"}),
            ("Scheduler and Refresh Coordinator summary", {"Scheduler"}),
            ("Repository, cache and persistence summary", {"Data and Cache"}),
            ("Provider summary", {"Providers"}),
            ("Configuration summary", {"Configuration"}),
            ("Documentation summary", {"Documentation"}),
        )
        for heading, categories in sections:
            lines.extend((f"## {heading}", ""))
            for item in snapshot.items:
                if item.category in categories:
                    lines.append(f"- **{item.status.value} — {self.redact(item.display_name)}:** {self.redact(item.summary)}")
            lines.append("")
        lines.extend(("## Latest diagnostics", "", json.dumps(self._redact_value(latest_diagnostic), ensure_ascii=False, indent=2, default=str) if latest_diagnostic else "No local diagnostic run is recorded.", "", "## Attention, degraded and failed items", ""))
        actionable = [item for item in snapshot.items if item.status in {HealthStatus.ATTENTION, HealthStatus.DEGRADED, HealthStatus.FAILED}]
        if not actionable:
            lines.extend(("No actionable health items.", ""))
        for item in actionable:
            lines.extend((f"- **{item.status.value} — {self.redact(item.display_name)}:** {self.redact(item.summary)}", f"  - Recommended action: {self.redact(item.recommended_action)}"))
        lines.extend(("", "## Complete safe health inventory", ""))
        for item in snapshot.items:
            lines.extend((f"### {item.status.value} — {self.redact(item.display_name)}", "", self.redact(item.summary), "", f"Source: {self.redact(item.source or 'Not available')}", f"Recommended action: {self.redact(item.recommended_action)}", "", "Details:", "```json", json.dumps(self._redact_value(item.details), ensure_ascii=False, indent=2, default=str), "```", ""))
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def run_local_diagnostics(self):
        """Run explicit, local diagnostics without contacting content providers."""

        started_at, started = datetime.now(timezone.utc), perf_counter()
        checks, errors = {}, []

        def run_check(key, callback):
            try:
                checks[key] = callback()
            except Exception as error:
                errors.append(f"{key}: {str(error)[:200]}")
                checks[key] = {"status": "FAILED", "error": str(error)[:200]}

        run_check("configuration", lambda: probe_configuration().to_dict())
        run_check("database", lambda: probe_database().to_dict())
        run_check("documentation", lambda: probe_documentation().to_dict())
        checked = datetime.now(timezone.utc)
        run_check("planning_cache", lambda: self._planning_item(checked).to_dict())
        run_check("repository_cache", lambda: [item.to_dict() for item in self._data_items(checked)])

        completed = datetime.now(timezone.utc)
        result = {
            **checks,
            "started_at": started_at.isoformat(), "completed_at": completed.isoformat(),
            "duration": perf_counter() - started,
            "status": "Passed" if not errors else "Partial" if len(errors) < len(checks) else "Failed",
            "errors": errors,
            "checks_passed": len(checks) - len(errors), "checks_total": len(checks),
        }
        self.health_state.record_diagnostic(self._redact_value(result))
        return result

    def recent_history(self, limit=5):
        return self.health_state.load().get("history", [])[-max(1, int(limit)):][::-1]

    @staticmethod
    def git_information() -> str:
        try:
            branch = subprocess.run(["git", "branch", "--show-current"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=2, check=True).stdout.strip() or "detached"
            commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=2, check=True).stdout.strip()
            state = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=2, check=True).stdout.splitlines()
            return f"branch {branch}; commit {commit}; {'clean' if not state else f'{len(state)} working-tree change(s)'}"
        except (OSError, subprocess.SubprocessError):
            return "Git information unavailable"

    def _application_item(self, now):
        closing = bool(getattr(self.runtime, "_closing", False)) if self.runtime else False
        return HealthItem("application", "NewsDesk Pro runtime", "Platform", HealthStatus.ATTENTION if closing else HealthStatus.HEALTHY, "Application shutdown is in progress." if closing else "Application runtime is available.", {"shutdown_state": "Closing" if closing else "Running", "window_available": bool(self.runtime)}, now, last_success=None if closing else now, source="Dashboard runtime state", recommended_action="Wait for shutdown to finish" if closing else "No action required")

    def _module_items(self, state, now):
        output = []
        module_state = state.get("modules") or {}
        policies = (state.get("scheduler") or {}).get("module_policies") or {}
        for definition in MODULE_DEFINITIONS:
            key = definition.key
            saved = module_state.get(key) or {}
            last_success = _parse_datetime(saved.get("last_successful_refresh"))
            latest_error = str(saved.get("latest_error_summary") or "")[:240]
            stored = self.repository.get_result(key)
            payload_present = stored is not None
            payload_errors = (
                list(stored.payload.get("errors") or ())
                if stored and isinstance(stored.payload, dict) else []
            )
            substantive_payload_errors = payload_errors
            if key == "council":
                substantive_payload_errors = [
                    error for error in payload_errors
                    if "image failure" not in str(error).casefold()
                    and "certificate" not in str(error).casefold()
                ]
            count = saved.get("latest_successful_count")
            policy = policies.get(key, {"mode": definition.default_schedule})
            stale = DashboardScheduler.module_is_stale(key, now.astimezone(), last_success, policy)
            if (latest_error or substantive_payload_errors) and payload_present:
                status, summary = HealthStatus.DEGRADED, "Latest refresh had errors; the prior runtime payload remains available."
            elif latest_error:
                status, summary = HealthStatus.ATTENTION, "Latest refresh failed and no runtime payload is available."
            elif last_success is None:
                status, summary = HealthStatus.ATTENTION, "Module has not recorded a successful refresh."
            elif stale:
                status, summary = HealthStatus.ATTENTION, "Module data is stale for its configured schedule."
            elif not payload_present:
                status, summary = HealthStatus.HEALTHY, "Prior refresh state is available; the full runtime payload loads during refresh."
            else:
                status, summary = HealthStatus.HEALTHY, "Module state is current with no recorded fatal error."
            next_run = DashboardScheduler.next_module_run(key, now.astimezone(), last_success, policy)
            details = {"configured": True, "latest_payload_count": count if count is not None else "Unknown", "repository_payload_present": payload_present, "last_successful_refresh": last_success.isoformat() if last_success else "Never", "scheduler_state": policy.get("mode", "Manual only"), "next_scheduled_run": next_run.isoformat() if next_run else "None", "latest_error": latest_error or "None", "retained_payload_errors": len(payload_errors), "non_image_payload_errors": len(substantive_payload_errors)}
            if status == HealthStatus.DEGRADED:
                recommendation = "Review source health; previous data has been retained"
            elif last_success is None:
                recommendation = "Run the module refresh"
            elif stale:
                recommendation = "Refresh the module and review its latest result"
            elif not payload_present:
                recommendation = "No action required; the scheduled startup refresh loads the runtime payload"
            else:
                recommendation = "No action required"
            output.append(HealthItem(f"module_{key}", definition.display_name, "Modules", status, summary, details, now, last_success=last_success, last_failure=_parse_datetime(saved.get("last_attempt")) if latest_error else None, source="Dashboard state, result repository and scheduler policy", recommended_action=recommendation))
        output.append(self._planning_item(now))
        output.extend(self._council_source_items(now))
        return output

    def _planning_item(self, now):
        cached = self.planning_cache.load()
        metadata = file_metadata(self.planning_cache.path)
        if cached:
            report = cached.report_data
            metadata.update({"schema_version": PLANNING_SCHEMA_VERSION, "schema_valid": True, "retained_application_count": cached.count, "newsworthy_count": int(report.get("newsworthy_stories", 0) or 0), "cache_timestamp": cached.completed_at.isoformat(), "report_available": True, "downloader_state": "Idle/not tracked"})
            return HealthItem("planning_cache", "Planning persistence", "Data and Cache", HealthStatus.HEALTHY, f"Valid retained Planning briefing with {cached.count} applications.", metadata, now, last_success=cached.completed_at, source="PlanningResultCache", related_path=str(self.planning_cache.path))
        status = HealthStatus.ATTENTION if self.planning_cache.path.exists() else HealthStatus.UNKNOWN
        metadata.update({"schema_version": PLANNING_SCHEMA_VERSION, "schema_valid": False, "report_available": False})
        return HealthItem("planning_cache", "Planning persistence", "Data and Cache", status, "Planning cache is unavailable or invalid." if status == HealthStatus.ATTENTION else "Awaiting the first retained Planning refresh.", metadata, now, source="PlanningResultCache", recommended_action="Run the Planning refresh", related_path=str(self.planning_cache.path))

    def _council_source_items(self, now):
        stored = self.repository.get_result("council")
        health = (stored.payload.get("source_health") or {}) if stored and isinstance(stored.payload, dict) else {}
        output = []
        for key, name in (("bassetlaw_district_council", "Bassetlaw District Council source"), ("nottinghamshire_county_council", "Nottinghamshire County Council source"), ("east_midlands_cca", "EMCCA articles")):
            value = health.get(key)
            if not value:
                output.append(HealthItem(f"council_{key}", name, "Modules", HealthStatus.UNKNOWN, "No runtime evidence available yet.", {"technical_reason": "Detailed Council source health is not persisted across application restarts."}, now, source="Council repository payload", recommended_action="Refresh Council to populate detailed source health"))
                continue
            successful = bool(value.get("successful"))
            failures = value.get("failures") or []
            status = HealthStatus.HEALTHY if successful else HealthStatus.DEGRADED
            output.append(HealthItem(f"council_{key}", name, "Modules", status, "Source completed successfully." if successful else "Source failed while Council may retain other sources.", {"articles": value.get("articles_found", value.get("stories_found", "Unknown")), "failures": failures[:5]}, now, last_success=now if successful else None, last_failure=now if failures else None, source="Council repository source_health", recommended_action="No action required" if successful else "Review source-health details"))
            if key == "east_midlands_cca":
                image_failures = [entry for entry in failures if str(entry).casefold().startswith("image for ")]
                output.append(HealthItem("emcca_images", "EMCCA images", "Data and Cache", HealthStatus.DEGRADED if image_failures else HealthStatus.HEALTHY, "Article images have retrieval warnings; article collection remains available." if image_failures else "No EMCCA image warning is recorded.", {"warnings": image_failures[:5]}, now, source="Council source-health image diagnostics", recommended_action="Wait for EMCCA to renew its image certificate" if image_failures else "No action required"))
        return output

    def _scheduler_items(self, state, now):
        settings = state.get("scheduler") or {}
        policies = settings.get("module_policies") or {}
        module_state = state.get("modules") or {}
        invalid = [key for key, policy in policies.items() if policy.get("mode") not in {"Off", "Manual only", "Daily", "Every 15 minutes", "Every 30 minutes", "Every 60 minutes", "Every 2 hours", "Every 12 hours", "Custom fixed times"}]
        last = {key: _parse_datetime((module_state.get(key) or {}).get("last_successful_refresh")) for key in policies}
        runs = DashboardScheduler.module_next_runs(now.astimezone(), policies, last)
        due = sorted((value, key) for key, value in runs.items() if value)
        next_time, next_key = due[0] if due else (None, "")
        scheduled = sum((policy.get("mode") not in {"Off", "Manual only"}) for policy in policies.values())
        scheduler_status = HealthStatus.ATTENTION if invalid else HealthStatus.HEALTHY
        scheduler = HealthItem("scheduler", "Dashboard scheduler", "Scheduler", scheduler_status, f"{scheduled} scheduled modules; {len(policies) - scheduled} off or manual-only.", {"running_state": "Active" if getattr(self.runtime, "scheduler_after_id", None) else "Not observed", "configured_scheduled_modules": scheduled, "off_or_manual_only": len(policies) - scheduled, "next_due_module": next_key or "None", "next_scheduled_time": next_time.isoformat() if next_time else "None", "overdue_jobs": sum(bool(value and value <= now.astimezone()) for value in runs.values()), "invalid_policies": invalid, "last_scheduler_tick": "Not tracked"}, now, source="DashboardStateStore and DashboardScheduler", recommended_action="Review scheduler policies" if invalid else "No action required")
        running = []
        if self.coordinator:
            running = [definition.key for definition in MODULE_DEFINITIONS if self.coordinator.is_running(definition.key)]
        heavy_limit = int(settings.get("max_heavy_collectors", 2) or 2)
        heavy_in_use = len(set(running) & set(HEAVY_MODULE_KEYS))
        coordinator_status = HealthStatus.FAILED if heavy_in_use > heavy_limit else HealthStatus.HEALTHY
        coordinator = HealthItem("refresh_coordinator", "Refresh Coordinator", "Scheduler", coordinator_status, f"{len(running)} active jobs; heavy usage {heavy_in_use} of {heavy_limit}.", {"active_jobs": running, "queued_jobs": "Not tracked", "heavy_worker_limit": heavy_limit, "heavy_workers_in_use": heavy_in_use, "light_workers_in_use": len(running) - heavy_in_use, "duplicate_prevention": "Active", "last_completed_job": (state.get("recent_runs") or [{}])[0].get("timestamp", "Unknown") if state.get("recent_runs") else "Unknown", "latest_coordinator_error": getattr(self.coordinator, "latest_planning_cache_error", "") or "None", "shutdown_state": "Closing" if getattr(self.runtime, "_closing", False) else "Running"}, now, source="DashboardRefreshCoordinator and Dashboard runtime", recommended_action="Review worker concurrency" if coordinator_status == HealthStatus.FAILED else "No action required")
        return [scheduler, coordinator]

    def _data_items(self, now):
        repository_items = []
        for definition in MODULE_DEFINITIONS:
            stored = self.repository.get_result(definition.key)
            count = self._payload_count(stored.payload) if stored else 0
            repository_items.append(HealthItem(f"repository_{definition.key}", f"{definition.display_name} runtime payload", "Data and Cache", HealthStatus.HEALTHY if stored else HealthStatus.UNKNOWN, f"Runtime payload present with {count} items." if stored else "Never observed in this process.", {"payload_present": bool(stored), "payload_count": count, "payload_timestamp": stored.completed_at.isoformat() if stored else "Unknown", "identity": f"runtime:{definition.key}" if stored else "None", "technical_reason": "Runtime payloads are intentionally not persisted by DashboardResultRepository." if not stored else "Available"}, now, last_success=stored.completed_at if stored else None, source="DashboardResultRepository", recommended_action="No action required" if stored else "Run the module refresh to populate its runtime payload"))
        cache = self.image_cache
        image_item = HealthItem("image_preview_cache", "Image preview cache", "Data and Cache", HealthStatus.HEALTHY, f"{len(cache)} of {cache.max_entries} preview entries are in use.", {"current_entries": len(cache), "maximum_entries": cache.max_entries, "hits": cache.hits, "misses": cache.misses, "eviction_count": "Not tracked", "invalid_image_count": "Not retained"}, now, source="Shared ImagePreviewCache", recommended_action="No action required")
        return [*repository_items, image_item]

    @staticmethod
    def _payload_count(payload):
        if not isinstance(payload, dict): return 0
        if "count" in payload: return int(payload.get("count") or 0)
        for key in ("stories", "announcements"):
            if isinstance(payload.get(key), list): return len(payload[key])
        return 0

    @classmethod
    def redact(cls, text):
        return SECRET_PATTERN.sub("REDACTED", str(text))

    @classmethod
    def _redact_value(cls, value):
        if isinstance(value, dict): return {cls.redact(key): cls._redact_value(item) for key, item in value.items() if not SECRET_PATTERN.search(str(key))}
        if isinstance(value, list): return [cls._redact_value(item) for item in value]
        if isinstance(value, tuple): return [cls._redact_value(item) for item in value]
        return cls.redact(value) if isinstance(value, str) else value
