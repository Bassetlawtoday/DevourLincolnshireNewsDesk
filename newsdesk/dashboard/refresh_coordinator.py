"""Independent module refresh coordination for NewsDesk Pro Home."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import threading
from typing import Callable

from newsdesk.services.fire_service import FireCollectionService
from newsdesk.services.council_service import CouncilCollectionService
from newsdesk.services.police_collection import PoliceCollectionService
from newsdesk.services.sport_collection import SportCollectionService
from services.planning_engine import run_weekly_download

from .government_feed import GovernmentFeedService
from .models import DashboardRefreshResult
from .planning_cache import PlanningResultCache
from .registry import MODULE_NAMES
from .result_repository import DashboardResultRepository
from .state_store import DashboardStateStore


LOGGER = logging.getLogger(__name__)
class _NullWidget:
    def configure(self, **_kwargs) -> None:
        pass


class _PlanningAdapter:
    """Supplies established Planning UI callbacks without touching Tk."""

    def __init__(self) -> None:
        self.downloaded = _NullWidget()
        self.newsworthiness = _NullWidget()
        self.report_data = None

    def write_log(self, message: str) -> None:
        LOGGER.debug("Planning dashboard refresh: %s", message)

    def set_progress(self, *_args) -> None:
        pass

    def set_status(self, *_args) -> None:
        pass

    def set_current_application(self, *_args) -> None:
        pass

    def set_list_progress(self, *_args) -> None:
        pass

    def set_report_data(self, value) -> None:
        self.report_data = value


class DashboardRefreshCoordinator:
    def __init__(
        self,
        state_store: DashboardStateStore | None = None,
        collectors: dict[str, Callable[[], object]] | None = None,
        result_repository: DashboardResultRepository | None = None,
        planning_cache: PlanningResultCache | None = None,
    ) -> None:
        self.state_store = state_store or DashboardStateStore()
        self.result_repository = result_repository or DashboardResultRepository()
        self.planning_cache = planning_cache or PlanningResultCache()
        self.latest_planning_cache_error = ""
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self.latest_government_result = None
        self.government_hours = 48
        self.collectors = collectors or {
            "planning": self._collect_planning,
            "police": self._collect_police,
            "fire": self._collect_fire,
            "sport": self._collect_sport,
            "council": self._collect_council,
            "government": self._collect_government,
            "events": self._collect_events,
            "content": self._collect_content,
        }

    def is_running(self, module_key: str) -> bool:
        with self._lock:
            return module_key in self._running

    def refresh_module(self, module_key: str) -> DashboardRefreshResult | None:
        with self._lock:
            if module_key in self._running:
                return None
            self._running.add(module_key)
        result = DashboardRefreshResult(module_key, MODULE_NAMES[module_key])
        payload = None
        try:
            collected = self.collectors[module_key]()
            result.count, payload = self._count_and_payload(collected)
            result.success = True
        except Exception as error:
            result.error_message = str(error)[:240] or error.__class__.__name__
            LOGGER.exception("Dashboard refresh failed for %s", module_key)
        finally:
            result.completed_at = datetime.now(timezone.utc)
            with self._lock:
                self._running.discard(module_key)
        if result.success:
            result.item_keys = self.item_keys(module_key, payload)
            result.updates_date = result.completed_at.astimezone().date().isoformat()
        if result.success and payload is not None:
            if module_key == "planning":
                try:
                    self.planning_cache.save(
                        payload["report_data"], result.completed_at
                    )
                    self.latest_planning_cache_error = ""
                except Exception as error:
                    self.latest_planning_cache_error = str(error)[:240]
                    LOGGER.exception("Could not persist Planning briefing cache")
            self.result_repository.set_result(
                module_key, payload, result.completed_at
            )
        self.record_result(result)
        return result

    def record_result(self, result: DashboardRefreshResult) -> None:
        with self._lock:
            state = self.state_store.load()
            previous = (state.get("modules") or {}).get(result.module_key, {})
            previous_count = previous.get("latest_successful_count")
            result.previous_count = previous_count
            result.change = result.count - previous_count if result.success and previous_count is not None else None
            module_state = dict(previous)
            module_state.update({
                "display_name": result.display_name,
                "latest_error_summary": result.error_message,
                "last_attempt": result.completed_at.isoformat() if result.completed_at else None,
                "last_duration": result.duration,
            })
            if result.success:
                current_keys = set(result.item_keys)
                previous_keys = set(previous.get("known_item_keys") or ())
                if not previous_keys:
                    new_keys = set()
                    known_order = list(result.item_keys)
                    tracking_started_at = result.completed_at.isoformat()
                else:
                    new_keys = current_keys - previous_keys
                    known_order = list(previous.get("known_item_keys") or ())
                    known_order.extend(sorted(new_keys))
                    tracking_started_at = str(
                        previous.get("tracking_started_at")
                        or result.completed_at.isoformat()
                    )
                if (
                    previous.get("updates_date") == result.updates_date
                    and previous.get("updates_basis") == "first_seen"
                ):
                    today_keys = set(previous.get("updates_today_keys") or ())
                else:
                    today_keys = set()
                today_keys.update(new_keys)
                result.updates_today = len(today_keys)
                result.tracking_started_at = tracking_started_at
                module_state.update({
                    "previous_successful_count": previous_count,
                    "latest_successful_count": result.count,
                    "last_successful_refresh": result.completed_at.isoformat(),
                    "last_change": result.change,
                    "updates_today": result.updates_today,
                    "updates_date": result.updates_date,
                    "updates_basis": "first_seen",
                    "updates_today_keys": sorted(today_keys),
                    "known_item_keys": known_order[-5000:],
                    "tracking_started_at": tracking_started_at,
                })
            state.setdefault("modules", {})[result.module_key] = module_state
            self.state_store.save(state)

    @staticmethod
    def calculate_change(previous_count: int | None, current_count: int) -> tuple[int | None, str]:
        if previous_count is None:
            return None, "Baseline established"
        change = current_count - previous_count
        if change > 0:
            return change, f"+{change} since previous refresh"
        if change < 0:
            return change, f"{change} since previous refresh"
        return 0, "No change"

    @staticmethod
    def format_updates_today(count: int) -> str:
        count = max(0, int(count or 0))
        if count == 0:
            return "No updates today"
        if count == 1:
            return "1 update today"
        return f"{count} updates today"

    @classmethod
    def item_keys(cls, module_key: str, payload: object | None) -> list[str]:
        if not isinstance(payload, dict):
            return []
        if module_key == "planning":
            report = payload.get("report_data") or {}
            items = report.get("all_applications") or [] if isinstance(report, dict) else []
            identities = (
                (item.get("reference"), item.get("address"), item.get("proposal"))
                for item in items if isinstance(item, dict)
            )
        else:
            items = payload.get("stories") or []
            identities = (
                (
                    item.get("story_id") or item.get("url") or item.get("title"),
                    item.get("source"),
                ) if isinstance(item, dict) else (
                    getattr(item, "story_id", "")
                    or getattr(item, "url", "")
                    or getattr(item, "title", ""),
                    getattr(item, "source", ""),
                )
                for item in items
            )
        keys = []
        for identity in identities:
            normalised = "|".join(
                " ".join(str(value or "").split()).casefold()
                for value in identity
            )
            if normalised.strip("|"):
                keys.append(hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:24])
        return list(dict.fromkeys(keys))

    @staticmethod
    def _count_and_payload(collected) -> tuple[int, object | None]:
        if isinstance(collected, tuple) and len(collected) == 2:
            return int(collected[0]), collected[1]
        return int(collected), None

    @staticmethod
    def _collect_planning() -> tuple[int, dict]:
        adapter = _PlanningAdapter()
        count = int(run_weekly_download(adapter))
        return count, {
            "report_data": adapter.report_data,
            "count": count,
        }

    @staticmethod
    def _collect_police() -> tuple[int, dict]:
        collection = PoliceCollectionService().collect()
        return collection.collected_count, {
            "stories": collection.stories,
            "publish_results": collection.publish_results,
            "errors": collection.errors,
        }

    @staticmethod
    def _collect_fire() -> tuple[int, dict]:
        collection = FireCollectionService().collect()
        return collection.collected_count, {
            "stories": collection.stories,
            "publish_results": collection.publish_results,
            "errors": collection.errors,
        }

    @staticmethod
    def _collect_sport() -> tuple[int, dict]:
        collection = SportCollectionService().collect()
        return collection.collected_count, {
            "stories": collection.stories,
            "publish_results": collection.publish_results,
            "errors": collection.errors,
        }

    @staticmethod
    def _collect_council() -> tuple[int, dict]:
        collection = CouncilCollectionService().collect()
        if not collection.successful:
            detail = "; ".join(collection.errors) or "All Council sources failed"
            raise RuntimeError(detail)
        return collection.collected_count, {
            "stories": collection.stories,
            "publish_results": collection.publish_results,
            "errors": collection.errors,
            "source_health": collection.source_health_payload(),
        }

    def _collect_government(self) -> tuple[int, dict]:
        self.latest_government_result = GovernmentFeedService().collect(
            hours=self.government_hours
        )
        announcements = self.latest_government_result.announcements
        return len(announcements), {"announcements": announcements}

    @staticmethod
    def _collect_events() -> tuple[int, dict]:
        from eventsdesk.harvest_engine import MidlandsHarvestEngine
        from eventsdesk.source_catalog import SourceCatalog
        from eventsdesk.source_scope import enabled_sources
        from modules.events import EVENTS_DATA_DIR, EVENTS_DATABASE, EVENTS_SUMMARY, get_event_dashboard_summary
        selected = enabled_sources(SourceCatalog.load_default(), EVENTS_DATA_DIR)
        if not selected:
            raise RuntimeError("No EventsDesk sources are enabled")
        result = MidlandsHarvestEngine().harvest(
            database=str(EVENTS_DATABASE), output=str(EVENTS_SUMMARY),
            source_ids=[source.id for source in selected], skip_network_preflight=False,
        )
        return int(get_event_dashboard_summary()["count"]), {"summary": result}

    @staticmethod
    def _collect_content() -> tuple[int, dict]:
        from contentdesk.collector import ContentExplorerCollector
        from contentdesk.config import load_api_key
        from contentdesk.storage import ContentStore
        key = load_api_key()
        if not key:
            raise RuntimeError("LDRS API key is not configured")
        with ContentExplorerCollector(key) as collector:
            rows = collector.collect_listings(limit=100)
        store = ContentStore()
        run_id = store.start_run("Latest 100")
        try:
            stored = store.upsert_many(rows)
            store.finish_run(run_id, discovered=len(rows), stored=stored, status="success")
        except Exception as exc:
            store.finish_run(run_id, discovered=0, stored=0, status="failed", message=str(exc))
            raise
        return int(store.summary()["count"]), {"stored": stored, "discovered": len(rows), "scope": "Latest 100"}
