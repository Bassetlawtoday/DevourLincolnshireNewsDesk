"""Independent module refresh coordination for NewsDesk Pro Home."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import threading
from typing import Callable

from newsdesk.services.council_service import CouncilCollectionService
from newsdesk.services.police_collection import PoliceCollectionService
from newsdesk.services.sport_collection import SportCollectionService

from .government_feed import GovernmentFeedService
from .models import DashboardRefreshResult
from .registry import MODULE_NAMES
from .result_repository import DashboardResultRepository
from .state_store import DashboardStateStore


LOGGER = logging.getLogger(__name__)
LDRS_DETAIL_LIMIT_PER_REFRESH = 12
LDRS_REQUEST_TIMEOUT_SECONDS = 15
class DashboardRefreshCoordinator:
    def __init__(
        self,
        state_store: DashboardStateStore | None = None,
        collectors: dict[str, Callable[[], object]] | None = None,
        result_repository: DashboardResultRepository | None = None,
    ) -> None:
        self.state_store = state_store or DashboardStateStore()
        self.result_repository = result_repository or DashboardResultRepository()
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self.latest_government_result = None
        self.government_hours = 48
        self.collectors = collectors or {
            "police": self._collect_police,
            "sport": self._collect_sport,
            "council": self._collect_council,
            "government": self._collect_government,
            "content": self._collect_content,
        }

    def is_running(self, module_key: str) -> bool:
        with self._lock:
            return module_key in self._running

    def refresh_module(self, module_key: str) -> DashboardRefreshResult | None:
        if module_key not in self.collectors or module_key not in MODULE_NAMES:
            raise ValueError(f"Module is not active: {module_key}")
        with self._lock:
            if module_key in self._running:
                return None
            self._running.add(module_key)
        result = DashboardRefreshResult(module_key, MODULE_NAMES[module_key])
        payload = None
        try:
            collected = self.collectors[module_key]()
            result.count, payload = self._count_and_payload(collected)
            if module_key in {"police", "sport", "council", "content"} and isinstance(payload, dict):
                stories = list(payload.get("stories") or [])
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                retained = [
                    story for story in stories
                    if (self._story_date(story) is None or self._story_date(story) >= cutoff)
                ]
                payload["stories"] = retained
                result.count = len(retained)
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
            if module_key in {"police", "sport", "council", "content"}:
                try:
                    self._stage_new_social_drafts(module_key, payload)
                except Exception:
                    # Social Desk is an editorial staging queue. A local draft
                    # storage problem must not turn a successful source refresh
                    # into a source failure.
                    LOGGER.exception(
                        "Could not stage %s refresh in Social Desk", module_key
                    )
            self.result_repository.set_result(
                module_key, payload, result.completed_at
            )
        self.record_result(result)
        return result

    def _stage_new_social_drafts(self, module_key: str, payload: dict) -> int:
        """Stage only newly discovered stories, without overwriting editors."""
        from newsdesk.social.selection import _story_identity, stage_story_for_social_desk
        from newsdesk.social.store import SocialDraftStore, SocialHandoffStore
        from newsdesk.social.text import clean_social_text
        from newsdesk.updates.content_gate import has_verified_full_content

        stories = payload.get("stage_stories")
        if stories is None:
            all_stories = list(payload.get("stories") or [])
            state = self.state_store.load()
            previous = (state.get("modules") or {}).get(module_key, {})
            known = set(previous.get("known_item_keys") or ())
            pending = set(previous.get("social_stage_pending_keys") or ())
            # The first successful refresh establishes a baseline. This avoids
            # flooding Social Desk with the complete historical source archive.
            if not known:
                return 0
            stories = []
            next_pending = set()
            social_store = SocialDraftStore()
            drafts = social_store.load() if module_key == "sport" else []
            for story in all_stories:
                story_keys = set(self.item_keys(module_key, {"stories": [story]}))
                is_new_or_pending = bool(story_keys - known or story_keys & pending)

                # A previous release could stage a listing teaser when it
                # already had an image. Upgrade only an untouched, unsent Sport
                # draft whose text is still exactly that source teaser.
                safe_teaser_upgrade = False
                if module_key == "sport" and has_verified_full_content("sport", story):
                    source_url = str(getattr(story, "url", "") or "").strip()
                    existing = social_store.find_by_source_url(drafts, source_url)
                    expected_teaser = clean_social_text(
                        getattr(story, "summary", ""), source_url=source_url
                    )
                    safe_teaser_upgrade = bool(
                        existing
                        and not str(existing.metricool_id or "").strip()
                        and str(existing.status or "") == "Sport draft"
                        and " ".join(str(existing.text or "").split()).casefold()
                        == " ".join(expected_teaser.split()).casefold()
                    )

                if module_key == "sport" and not has_verified_full_content("sport", story):
                    if is_new_or_pending:
                        next_pending.update(story_keys)
                    continue
                if is_new_or_pending or safe_teaser_upgrade:
                    stories.append((story, safe_teaser_upgrade))

            if module_key == "sport":
                state.setdefault("modules", {}).setdefault(module_key, {})[
                    "social_stage_pending_keys"
                ] = sorted(next_pending)
                self.state_store.save(state)
        else:
            stories = [(story, False) for story in stories]

        handoffs = SocialHandoffStore()
        created = 0
        upgraded = 0
        for story, safe_teaser_upgrade in stories:
            if handoffs.is_deleted(_story_identity(story, module_key)) and not safe_teaser_upgrade:
                continue
            _draft, was_created = stage_story_for_social_desk(
                story,
                module_key=module_key,
                update_existing=safe_teaser_upgrade,
            )
            created += int(was_created)
            upgraded += int(safe_teaser_upgrade and not was_created)
        payload["social_drafts_staged"] = created
        payload["social_drafts_upgraded"] = upgraded
        return created

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
    def _collect_police() -> tuple[int, dict]:
        collection = PoliceCollectionService().collect()
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
            "source_health": collection.source_health,
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
    def _collect_content() -> tuple[int, dict]:
        from contentdesk.collector import ContentExplorerCollector, _is_lincolnshire_record
        from contentdesk.config import load_api_key, load_settings
        from contentdesk.storage import ContentStore
        from modules.content import SCOPE_LIMITS, _story_from_row, get_current_content_stories
        from newsdesk.updates.content_gate import has_verified_full_content
        from newsdesk.social.selection import _story_identity
        from newsdesk.social.store import SocialHandoffStore

        key = load_api_key()
        if not key:
            raise RuntimeError("LDRS API key is not configured")

        settings = load_settings()
        scope = str(settings.get("default_scope") or "Latest 500").strip()
        if scope not in SCOPE_LIMITS:
            scope = "Latest 500"
        listing_limit = SCOPE_LIMITS[scope]

        store = ContentStore()
        run_id = store.start_run(scope)
        rows = []
        stored = 0
        stage_stories = []
        detail_errors = []
        deferred_details = 0
        detail_attempts = 0
        repaired = 0
        handed_off = 0
        outside_window = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        handoffs = SocialHandoffStore()
        try:
            with ContentExplorerCollector(
                key, timeout=LDRS_REQUEST_TIMEOUT_SECONDS
            ) as collector:
                rows = collector.collect_listings(limit=listing_limit)

                # Match the working Local Democracy module: persist every
                # listing before attempting any bounded detail downloads.
                # Otherwise records after the detail limit disappear entirely.
                existing_rows = {
                    str(listing.get("article_id") or "").strip(): store.get(
                        str(listing.get("article_id") or "").strip()
                    )
                    for listing in rows
                    if str(listing.get("article_id") or "").strip()
                }
                stored = store.upsert_many(rows)

                # The LDRS feed is national. Spend the bounded detail-download
                # budget on Lincolnshire candidates, not on the first national
                # records returned by the API.
                local_listings = [
                    listing for listing in rows if _is_lincolnshire_record(listing)
                ]
                for listing in local_listings:
                    article_id = str(listing.get("article_id") or "").strip()
                    existing_row = existing_rows.get(article_id)
                    existing_story = _story_from_row(existing_row) if existing_row else None
                    needs_detail = (
                        existing_story is None
                        or not has_verified_full_content("content", existing_story)
                    )
                    if not needs_detail:
                        store.upsert_many([listing])
                        story = existing_story
                        stamp = DashboardRefreshCoordinator._story_date(story)
                        if stamp and stamp < cutoff:
                            outside_window += 1
                        elif handoffs.is_deleted(_story_identity(story, "content")):
                            handed_off += 1
                        else:
                            stage_stories.append(story)
                        continue
                    if detail_attempts >= LDRS_DETAIL_LIMIT_PER_REFRESH:
                        deferred_details += 1
                        continue
                    detail_attempts += 1
                    try:
                        detail = collector.fetch_detail(article_id)
                        complete = {**listing, **detail}
                        for field in ("authorities", "categories"):
                            if not complete.get(field):
                                complete[field] = listing.get(field) or []
                        if not str(complete.get("body") or "").strip():
                            raise RuntimeError("LDRS full article body was empty")
                        store.upsert_many([complete])
                        stored_row = store.get(article_id)
                        if stored_row is None:
                            raise RuntimeError("LDRS full article was not stored")
                        story = _story_from_row(stored_row)
                        if not has_verified_full_content("content", story):
                            raise RuntimeError("LDRS article did not pass the full-content check")
                        stamp = DashboardRefreshCoordinator._story_date(story)
                        if stamp and stamp < cutoff:
                            outside_window += 1
                        elif handoffs.is_deleted(_story_identity(story, "content")):
                            handed_off += 1
                        else:
                            stage_stories.append(story)
                        repaired += int(existing_row is not None)
                    except Exception as error:
                        detail_errors.append(f"{article_id}: {error}")
                        LOGGER.exception(
                            "Could not download complete LDRS article %s; it was not staged",
                            article_id,
                        )
            store.finish_run(
                run_id, discovered=len(rows), stored=stored, status="success"
            )
        except Exception as exc:
            store.finish_run(
                run_id,
                discovered=len(rows),
                stored=stored,
                status="failed",
                message=str(exc),
            )
            raise

        all_stories = get_current_content_stories()
        return int(store.summary()["count"]), {
            "stored": stored,
            "discovered": len(rows),
            "scope": scope,
            "stories": all_stories,
            "stage_stories": stage_stories,
            "full_articles_staged": len(stage_stories),
            "stored_articles_repaired": repaired,
            "detail_downloads_attempted": detail_attempts,
            "detail_downloads_deferred": deferred_details,
            "already_handed_off": handed_off,
            "outside_recovery_window": outside_window,
            "detail_errors": detail_errors,
            "errors": detail_errors,
        }

    @staticmethod
    def _story_date(story) -> datetime | None:
        value = str(getattr(story, "published", "") or "").strip()
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None

