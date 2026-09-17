"""NewsDesk Pro Home: the cover dashboard for newsroom intelligence."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
import logging
from pathlib import Path
import subprocess
import sys
import threading
from time import perf_counter
import webbrowser

import customtkinter as ctk
from PIL import Image
from newsdesk.display_dates import format_uk_datetime
from newsdesk.theme import ACTION_BLUE, ACTION_BLUE_HOVER, LOGO_PATH

from modules.fire import open_fire
from modules.system_health import open_system_health
from modules.data_retention import open_data_retention
from modules.social_desk import open_social_desk
from modules.council import open_council
from modules.events import open_events, get_event_dashboard_summary
from modules.content import open_content, get_content_dashboard_summary
from modules.planning import PlanningWindow
from modules.planning_report import open_planning_report
from modules.police import open_police
from modules.sport import open_sport
from newsdesk.dashboard.branding import load_branding
from newsdesk.dashboard.refresh_coordinator import DashboardRefreshCoordinator
from newsdesk.dashboard.registry import (
    CARD_MODULE_KEYS,
    HEAVY_MODULE_KEYS,
    MODULE_NAMES,
)
from newsdesk.dashboard.planning_cache import PlanningResultCache
from newsdesk.dashboard.result_repository import DashboardResultRepository
from newsdesk.dashboard.scheduler import DashboardScheduler
from newsdesk.dashboard.state_store import DashboardStateStore
from newsdesk.ui_support import focus_existing_window, track_window_reference


LOGGER = logging.getLogger(__name__)
APP_BG = "#0f172a"
HEADER_BG = "#111827"
CARD_BG = "#1f2937"
ACCENT = "#dc2626"
ACCENT_HOVER = "#b91c1c"
TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#cbd5e1"
TEXT_MUTED = "#94a3b8"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"
BORDER = "#334155"
MODULE_KEYS = CARD_MODULE_KEYS
POLICY_OPTIONS = {
    "planning": ("Off", "Daily", "Every 12 hours", "Manual only"),
    "police": ("Off", "Every 30 minutes", "Every 60 minutes", "Every 2 hours", "Manual only"),
    "fire": ("Off", "Every 30 minutes", "Every 60 minutes", "Every 2 hours", "Manual only"),
    "sport": ("Off", "Every 30 minutes", "Every 60 minutes", "Every 2 hours", "Manual only"),
    "council": ("Off", "Every 30 minutes", "Every 60 minutes", "Every 2 hours", "Manual only"),
    "government": ("Off", "Every 15 minutes", "Every 30 minutes", "Every 60 minutes", "Manual only"),
    "events": ("Off", "Every 2 hours", "Every 12 hours", "Manual only"),
    "content": ("Off", "Every 30 minutes", "Every 60 minutes", "Every 2 hours", "Manual only"),
}


class Dashboard(ctk.CTkFrame):
    """NewsDesk Pro Home dashboard."""

    def __init__(self, master):
        super().__init__(master, fg_color=APP_BG)
        self.master = master
        self.branding = load_branding()
        self.state_store = DashboardStateStore()
        self.state = self.state_store.load()
        self.result_repository = DashboardResultRepository()
        self.planning_cache = PlanningResultCache()
        self.coordinator = DashboardRefreshCoordinator(
            self.state_store,
            result_repository=self.result_repository,
            planning_cache=self.planning_cache,
        )
        heavy_limit = max(
            1, int(self.state["scheduler"].get("max_heavy_collectors", 2))
        )
        self.executor = ThreadPoolExecutor(
            max_workers=heavy_limit + 2, thread_name_prefix="newsdesk-home"
        )
        self.heavy_semaphore = threading.BoundedSemaphore(heavy_limit)
        self.futures: dict[str, Future] = {}
        self._active_refreshes: set[str] = set()
        self.module_windows: dict[str, object] = {}
        self.card_widgets: dict[str, dict[str, object]] = {}
        self.announcements = []
        self.scheduler_after_id = None
        self.clock_after_id = None
        self.next_refresh_at = None
        self.last_scheduled_windows: set[str] = set()
        self._closing = False
        self._run_started_at = None
        self._run_results = {}
        self.planning_results_window = None
        self.planning_downloader_window = None
        self._hydrate_planning_cache()
        self.pack(fill="both", expand=True)
        self._configure_window()
        self._build_layout()
        self._restore_state()
        self._schedule_clock()
        self._reschedule()
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.state["scheduler"].get("refresh_on_startup", True):
            self.master.after(800, self._assess_startup_freshness)

    def _configure_window(self):
        self.master.minsize(1180, 760)
        self.master.configure(fg_color=APP_BG)
        self.master.title(f"{self.branding['product_name']} — {self.branding['newsroom_name']}")

    def _build_layout(self):
        self._build_header()
        body = ctk.CTkScrollableFrame(self, fg_color=APP_BG, corner_radius=0)
        body.pack(fill="both", expand=True)
        content = ctk.CTkFrame(body, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=28, pady=22)
        self._build_module_cards(content)
        self._build_government_feed(content)
        self._build_recent_runs(content)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=118)
        header.pack(fill="x")
        header.pack_propagate(False)
        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=28, pady=12)
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_columnconfigure(2, weight=1)
        logo = ctk.CTkFrame(inner, width=68, height=68, fg_color=CARD_BG, border_width=2, border_color=ACCENT, corner_radius=14)
        logo.grid(row=0, column=0, sticky="w", padx=(0, 14))
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="NDP", font=("Arial", 20, "bold"), text_color=TEXT_PRIMARY).place(relx=.5, rely=.5, anchor="center")
        if LOGO_PATH.exists():
            with Image.open(LOGO_PATH) as logo_file:
                newsroom_logo_source = logo_file.copy()
            self.newsroom_logo = ctk.CTkImage(
                light_image=newsroom_logo_source,
                dark_image=newsroom_logo_source,
                size=(68, 68),
            )
            ctk.CTkLabel(
                inner, text="", image=self.newsroom_logo
            ).grid(row=0, column=1, sticky="w", padx=(0, 14))
        brand = ctk.CTkFrame(inner, fg_color="transparent")
        brand.grid(row=0, column=2, sticky="w")
        ctk.CTkLabel(brand, text=self.branding["product_name"], font=("Arial", 29, "bold"), text_color=TEXT_PRIMARY, anchor="w").pack(anchor="w")
        ctk.CTkLabel(brand, text=f"{self.branding['newsroom_name']} newsroom", font=("Arial", 14), text_color=TEXT_SECONDARY, anchor="w").pack(anchor="w", pady=(2, 0))
        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.grid(row=0, column=3, sticky="e")
        summary = ctk.CTkFrame(actions, fg_color="transparent")
        summary.pack(anchor="e", fill="x")
        self.clock_label = ctk.CTkLabel(summary, text="", font=("Arial", 13, "bold"), text_color=TEXT_PRIMARY)
        self.clock_label.pack(side="right")
        self.dashboard_status_label = ctk.CTkLabel(summary, text="Ready", font=("Arial", 12), text_color=TEXT_SECONDARY)
        self.dashboard_status_label.pack(side="right", padx=(0, 18))
        row = ctk.CTkFrame(actions, fg_color="transparent")
        row.pack(anchor="e", pady=(4, 0))
        # Retain the widget for scheduler compatibility without displaying it.
        self.next_refresh_label = ctk.CTkLabel(row, text="")
        ctk.CTkButton(
            row, text="SOCIAL DESK", width=112,
            fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER,
            command=self._open_social_desk,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row, text="SYSTEM HEALTH", width=135,
            fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER,
            command=self._open_system_health,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row, text="DATA RETENTION", width=135,
            fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER,
            command=self._open_data_retention,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row, text="SETTINGS", width=86,
            fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER,
            command=self._open_scheduler_settings,
        ).pack(side="left", padx=(0, 8))
        self.refresh_all_button = ctk.CTkButton(row, text="REFRESH ALL", width=130, font=("Arial", 12, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.refresh_all)
        self.refresh_all_button.pack(side="left")

    def _build_module_cards(self, parent):
        heading = ctk.CTkFrame(parent, fg_color="transparent")
        heading.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(heading, text="INTELLIGENCE OVERVIEW", font=("Arial", 16, "bold"), text_color=TEXT_PRIMARY).pack(side="left")
        self.refresh_time_label = ctk.CTkLabel(heading, text="Last successful dashboard refresh: Never", font=("Arial", 12), text_color=TEXT_MUTED)
        self.refresh_time_label.pack(side="right")
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 20))
        for column in range(4):
            grid.grid_columnconfigure(column, weight=1, uniform="home-modules")
        for index, key in enumerate(MODULE_KEYS):
            row, column = divmod(index, 4)
            self._build_module_card(grid, key).grid(
                row=row, column=column, sticky="nsew", padx=6, pady=6
            )
        index = len(MODULE_KEYS)
        row, column = divmod(index, 4)
        self._build_events_card(grid).grid(
            row=row, column=column, sticky="nsew", padx=6, pady=6
        )
        index += 1
        row, column = divmod(index, 4)
        self._build_content_card(grid).grid(
            row=row, column=column, sticky="nsew", padx=6, pady=6
        )

    def _build_module_card(self, parent, key):
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=BORDER)
        ctk.CTkLabel(card, text=MODULE_NAMES[key], font=("Arial", 16, "bold"), text_color=TEXT_PRIMARY, anchor="w").pack(fill="x", padx=17, pady=(16, 8))
        count = ctk.CTkLabel(card, text="—", font=("Arial", 30, "bold"), text_color=TEXT_PRIMARY, anchor="w")
        count.pack(fill="x", padx=17)
        change = ctk.CTkLabel(card, text="Not yet refreshed", font=("Arial", 12), text_color=TEXT_MUTED, anchor="w")
        change.pack(fill="x", padx=17, pady=(2, 7))
        updated = ctk.CTkLabel(card, text="Last updated: Never", font=("Arial", 11), text_color=TEXT_MUTED, anchor="w")
        updated.pack(fill="x", padx=17)
        status = ctk.CTkLabel(card, text="Not yet refreshed", font=("Arial", 12, "bold"), text_color=TEXT_MUTED, anchor="w")
        status.pack(fill="x", padx=17, pady=(5, 12))
        ctk.CTkButton(
            card, text="OPEN", height=34,
            fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER,
            command=lambda value=key: self._open_module(value),
        ).pack(fill="x", padx=17, pady=(0, 16))
        self.card_widgets[key] = {"count": count, "change": change, "updated": updated, "status": status}
        return card

    def _build_events_card(self, parent):
        summary = get_event_dashboard_summary()
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=BORDER)
        ctk.CTkLabel(card, text="Events Intelligence", font=("Arial", 16, "bold"), text_color=TEXT_PRIMARY, anchor="w").pack(fill="x", padx=17, pady=(16, 8))
        self.events_count_label = ctk.CTkLabel(card, text=f"{summary['count']:,} current events", font=("Arial", 30, "bold"), text_color=TEXT_PRIMARY, anchor="w")
        self.events_count_label.pack(fill="x", padx=17)
        change = ctk.CTkLabel(card, text="Independent EventsDesk dataset", font=("Arial", 12), text_color=TEXT_MUTED, anchor="w")
        change.pack(fill="x", padx=17, pady=(2, 7))
        updated = str(summary.get("updated") or "Never").strip()
        if updated and updated != "Never":
            try:
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00")).strftime("%d %b %Y %H:%M")
            except ValueError:
                pass
        updated_label = ctk.CTkLabel(
            card, text=f"Last updated: {updated}", font=("Arial", 11),
            text_color=TEXT_MUTED, anchor="w",
        )
        updated_label.pack(fill="x", padx=17)
        self.events_status_label = ctk.CTkLabel(card, text=summary["status"], font=("Arial", 12, "bold"), text_color=SUCCESS if summary["count"] else TEXT_MUTED, anchor="w")
        self.events_status_label.pack(fill="x", padx=17, pady=(5, 12))
        ctk.CTkButton(card, text="OPEN", height=34, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self._open_events).pack(fill="x", padx=17, pady=(0, 16))
        self.card_widgets["events"] = {"count": self.events_count_label, "change": change, "updated": updated_label, "status": self.events_status_label}
        return card

    def _open_events(self):
        existing = self.module_windows.get("events")
        if focus_existing_window(existing):
            return existing
        module = open_events(self.master)
        track_window_reference(self.module_windows, "events", module)
        return module

    def _build_content_card(self, parent):
        summary = get_content_dashboard_summary()
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14, border_width=1, border_color=BORDER)
        ctk.CTkLabel(card, text="Local Democracy Intelligence", font=("Arial", 16, "bold"), text_color=TEXT_PRIMARY, anchor="w").pack(fill="x", padx=17, pady=(16, 8))
        count_label=ctk.CTkLabel(card, text=f"{summary['count']:,} stored stories", font=("Arial", 30, "bold"), text_color=TEXT_PRIMARY, anchor="w"); count_label.pack(fill="x", padx=17)
        latest = int(summary.get("latest_discovered") or 0)
        change=ctk.CTkLabel(card, text=f"Latest refresh: {latest:,} LDRS stories" if latest else "LDRS Content Explorer", font=("Arial", 12), text_color=TEXT_MUTED, anchor="w"); change.pack(fill="x", padx=17, pady=(2, 7))
        updated = str(summary.get("updated") or "Never").strip()
        if updated and updated != "Never":
            try:
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00")).strftime("%d %b %Y %H:%M")
            except ValueError:
                pass
        updated_label=ctk.CTkLabel(card, text=f"Last updated: {updated}", font=("Arial", 11), text_color=TEXT_MUTED, anchor="w"); updated_label.pack(fill="x", padx=17)
        status=ctk.CTkLabel(card, text=summary["status"], font=("Arial", 12, "bold"), text_color=SUCCESS if summary["count"] else TEXT_MUTED, anchor="w"); status.pack(fill="x", padx=17, pady=(5, 12))
        ctk.CTkButton(card, text="OPEN", height=34, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self._open_content).pack(fill="x", padx=17, pady=(0, 16))
        self.card_widgets["content"]={"count":count_label,"change":change,"updated":updated_label,"status":status}
        return card

    def _open_content(self):
        existing = self.module_windows.get("content")
        if focus_existing_window(existing):
            return existing
        module = open_content(self.master)
        track_window_reference(self.module_windows, "content", module)
        return module

    def _open_social_desk(self):
        existing = self.module_windows.get("social")
        if focus_existing_window(existing):
            return existing
        module = open_social_desk(self.master)
        track_window_reference(self.module_windows, "social", module)
        return module

    def _build_government_feed(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=HEADER_BG, corner_radius=14, border_width=1, border_color=BORDER)
        panel.pack(fill="x", pady=(0, 20))
        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 8))
        ctk.CTkLabel(top, text="Government / National Announcements", font=("Arial", 16, "bold"), text_color=TEXT_PRIMARY).pack(side="left")
        self.feed_health_label = ctk.CTkLabel(top, text="Not yet refreshed", font=("Arial", 11), text_color=TEXT_MUTED)
        self.feed_health_label.pack(side="right")
        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.pack(fill="x", padx=18, pady=(0, 8))
        self.feed_search = ctk.CTkEntry(controls, placeholder_text="Search announcements...", width=260)
        self.feed_search.pack(side="left", padx=(0, 8))
        self.feed_search.bind("<KeyRelease>", lambda _event: self._render_feed())
        self.publisher_menu = ctk.CTkOptionMenu(
            controls, values=["All publishers"], width=230,
            fg_color=ACTION_BLUE, button_color=ACTION_BLUE,
            button_hover_color=ACTION_BLUE_HOVER,
            command=lambda _value: self._render_feed(),
        )
        self.publisher_menu.pack(side="left", padx=(0, 8))
        self.range_menu = ctk.CTkOptionMenu(
            controls, values=["Last 24 hours", "Last 48 hours", "Last 7 days"], width=145,
            fg_color=ACTION_BLUE, button_color=ACTION_BLUE,
            button_hover_color=ACTION_BLUE_HOVER,
            command=lambda _value: self._refresh_feed_only(),
        )
        self.range_menu.set("Last 48 hours")
        self.range_menu.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            controls, text="Refresh Feed", width=110,
            fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER,
            command=self._refresh_feed_only,
        ).pack(side="left")
        self.feed_count_label = ctk.CTkLabel(controls, text="0 of 0 announcements", text_color=TEXT_MUTED)
        self.feed_count_label.pack(side="right")
        self.feed_list = ctk.CTkScrollableFrame(panel, fg_color=CARD_BG, height=220, corner_radius=10)
        self.feed_list.pack(fill="x", padx=18, pady=(0, 16))
        self._render_feed()

    def _build_recent_runs(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=HEADER_BG, corner_radius=14, border_width=1, border_color=BORDER)
        panel.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(panel, text="RECENT DASHBOARD REFRESHES", font=("Arial", 14, "bold"), text_color=TEXT_PRIMARY, anchor="w").pack(fill="x", padx=18, pady=(13, 7))
        self.recent_runs_frame = ctk.CTkFrame(panel, fg_color="transparent")
        self.recent_runs_frame.pack(fill="x", padx=18, pady=(0, 13))
        self._render_recent_runs()

    def refresh_all(self):
        if self._closing:
            return
        self._run_started_at = datetime.now().astimezone()
        self._run_results = {}
        for key in ("government", "fire", "council", "police", "sport", "planning", "events", "content"):
            self._start_refresh(key)
        self.dashboard_status_label.configure(text="Refreshing modules…", text_color=WARNING)

    def _start_refresh(self, key):
        if key in self.futures and not self.futures[key].done():
            return
        if not any(not future.done() for future in self.futures.values()):
            self._run_results = {}
            self._run_started_at = datetime.now().astimezone()
        if key in self.card_widgets:
            self.card_widgets[key]["status"].configure(text="Waiting to refresh", text_color=WARNING)
        self.futures[key] = self.executor.submit(self._run_refresh_worker, key)
        self.master.after(100, lambda value=key: self._poll_future(value))

    def _run_refresh_worker(self, key):
        active_refreshes = getattr(self, "_active_refreshes", None)
        if active_refreshes is None:
            active_refreshes = self._active_refreshes = set()
        semaphore = self.heavy_semaphore if key in HEAVY_MODULE_KEYS else None
        if semaphore is not None:
            semaphore.acquire()
        try:
            active_refreshes.add(key)
            return self.coordinator.refresh_module(key)
        finally:
            active_refreshes.discard(key)
            if semaphore is not None:
                semaphore.release()

    def _mark_refreshing(self, key):
        if key in self.card_widgets:
            self.card_widgets[key]["status"].configure(
                text="Refreshing…", text_color=WARNING
            )

    def _poll_future(self, key):
        if self._closing:
            return
        future = self.futures.get(key)
        if future is None or not future.done():
            if key in self._active_refreshes:
                self._mark_refreshing(key)
            self.master.after(150, lambda value=key: self._poll_future(value))
            return
        try:
            result = future.result()
        except Exception as error:
            LOGGER.exception("Dashboard worker failed for %s", key)
            self.dashboard_status_label.configure(text=f"{MODULE_NAMES[key]} failed: {error}", text_color=ACCENT)
            return
        if result is None:
            return
        self._run_results[key] = result
        if key in self.card_widgets:
            self._update_card(result)
        elif key == "government":
            self._update_government_feed(result)
        if not any(not value.done() for value in self.futures.values()):
            self._complete_dashboard_run()

    def _update_card(self, result, load_open_module=True):
        widgets = self.card_widgets[result.module_key]
        widgets["status"].configure(
            text="Completed — Live data available" if result.success else "Failed — View details",
            text_color=SUCCESS if result.success else ACCENT,
        )
        if not result.success:
            return
        if result.module_key == "planning": count_text=f"{result.count} results"
        elif result.module_key == "events": count_text=f"{result.count:,} current events"
        elif result.module_key == "content": count_text=f"{result.count:,} stored stories"
        else: count_text=f"{result.count} stories"
        widgets["count"].configure(text=count_text)
        updates_text = self._updates_label(
            result.updates_today, result.updates_date,
            result.tracking_started_at,
        )
        if result.module_key == "content":
            latest = int(get_content_dashboard_summary().get("latest_discovered") or 0)
            updates_text = f"Latest refresh: {latest:,} LDRS stories"
        widgets["change"].configure(
            text=updates_text,
            text_color=SUCCESS if result.updates_today > 0 else TEXT_MUTED,
        )
        widgets["updated"].configure(text=f"Last updated: {result.completed_at.astimezone().strftime('%H:%M')}")
        if load_open_module:
            self._load_payload_into_open_module(result.module_key)

    def _load_payload_into_open_module(self, key):
        if key in {"events", "content"}:
            module = self.module_windows.get(key)
            if module is not None and hasattr(module, "refresh_database"):
                try: module.refresh_database()
                except Exception: LOGGER.debug("Could not refresh open %s database", key, exc_info=True)
            return
        if key == "planning":
            stored = self.result_repository.get_result("planning")
            existing = self.planning_results_window
            try:
                if stored and existing and existing.window.winfo_exists():
                    existing.load_results(stored.payload["report_data"])
            except Exception:
                LOGGER.debug("Could not refresh open Planning briefing", exc_info=True)
            return
        module = self.module_windows.get(key)
        if module is None:
            return
        window = getattr(module, "window", module)
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return
        if getattr(module, "is_refreshing", False) or getattr(module, "running", False):
            return
        stored = self.result_repository.get_result(key)
        if stored is not None:
            self._load_module_payload(key, module, stored.payload)

    def _update_government_feed(self, result):
        feed_result = self.coordinator.latest_government_result
        if result.success and feed_result:
            self.announcements = list(feed_result.announcements)
            self.feed_health_label.configure(text=f"{feed_result.successful} of {feed_result.attempted} official feeds updated successfully", text_color=SUCCESS if not feed_result.failures else WARNING)
            publishers = sorted({item.publisher for item in self.announcements}, key=str.casefold)
            current = self.publisher_menu.get()
            self.publisher_menu.configure(values=["All publishers", *publishers])
            self.publisher_menu.set(current if current in publishers else "All publishers")
            self._render_feed()
        else:
            self.feed_health_label.configure(text="Feed refresh failed", text_color=ACCENT)

    def _complete_dashboard_run(self):
        results = list(self._run_results.values())
        if not results:
            return
        successes = sum(result.success for result in results)
        status = "success" if successes == len(results) else "partial" if successes else "failure"
        state = self.state_store.load()
        row = {"timestamp": datetime.now().astimezone().isoformat(), "status": status}
        for key, result in self._run_results.items():
            row[key] = result.count if result.success else None
        state["recent_runs"] = [row, *(state.get("recent_runs") or [])][:5]
        self.state_store.save(state)
        self.state = state
        successful_times = [result.completed_at for result in results if result.success]
        if successful_times:
            latest = max(successful_times)
            self.refresh_time_label.configure(text=f"Last successful dashboard refresh: {latest.astimezone().strftime('%d %b %Y %H:%M')}")
        self.dashboard_status_label.configure(text="Refresh completed" if status == "success" else "Refresh completed with source failures", text_color=SUCCESS if status == "success" else WARNING)
        self._render_recent_runs()
        self._reschedule()

    def _render_feed(self):
        for child in self.feed_list.winfo_children():
            child.destroy()
        query = self.feed_search.get().strip().casefold() if hasattr(self, "feed_search") else ""
        publisher = self.publisher_menu.get() if hasattr(self, "publisher_menu") else "All publishers"
        visible = [item for item in self.announcements if (publisher == "All publishers" or item.publisher == publisher) and (not query or query in f"{item.title} {item.publisher} {item.description}".casefold())]
        if not visible:
            ctk.CTkLabel(self.feed_list, text="No announcements match the current filters.", text_color=TEXT_MUTED).pack(pady=25)
        for item in visible:
            row = ctk.CTkFrame(self.feed_list, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(row, text=format_uk_datetime(item.published_at), width=165, anchor="w", text_color=TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=item.publisher, width=205, anchor="w", text_color=TEXT_SECONDARY).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text=item.title, anchor="w", fg_color="transparent", hover_color="#374151", command=lambda url=item.canonical_url: webbrowser.open(url)).pack(side="left", fill="x", expand=True)
        if hasattr(self, "feed_count_label"):
            self.feed_count_label.configure(text=f"{len(visible)} of {len(self.announcements)} announcements")

    def _refresh_feed_only(self):
        hours = {"Last 24 hours": 24, "Last 48 hours": 48, "Last 7 days": 168}.get(self.range_menu.get(), 48)
        self.coordinator.government_hours = hours
        self._start_refresh("government")

    def _restore_state(self):
        latest = []
        for key in (*MODULE_KEYS, "events", "content"):
            stored = (self.state.get("modules") or {}).get(key, {})
            widgets = self.card_widgets[key]
            count = stored.get("latest_successful_count")
            if count is not None:
                if key == "planning": count_text=f"{count} results"
                elif key == "events": count_text=f"{count:,} current events"
                elif key == "content": count_text=f"{count:,} stored stories"
                else: count_text=f"{count} stories"
                widgets["count"].configure(text=count_text)
                today = datetime.now().astimezone().date().isoformat()
                updates_today = (
                    int(stored.get("updates_today") or 0)
                    if stored.get("updates_date") == today
                    and stored.get("updates_basis") == "first_seen"
                    else 0
                )
                widgets["change"].configure(
                    text=self._updates_label(
                        updates_today,
                        str(stored.get("updates_date") or ""),
                        str(stored.get("tracking_started_at") or ""),
                    ),
                    text_color=SUCCESS if updates_today > 0 else TEXT_MUTED,
                )
                if key == "content":
                    latest_story_count = int(get_content_dashboard_summary().get("latest_discovered") or 0)
                    widgets["change"].configure(text=f"Latest refresh: {latest_story_count:,} LDRS stories", text_color=TEXT_MUTED)
                widgets["status"].configure(
                    text=("Completed — local data available" if key in {"events", "content"}
                          else "Previous-session count — payload unavailable"),
                    text_color=SUCCESS if key in {"events", "content"} else WARNING,
                )
            refreshed = stored.get("last_successful_refresh")
            if refreshed:
                parsed = datetime.fromisoformat(refreshed).astimezone()
                latest.append(parsed)
                widgets["updated"].configure(text=f"Last updated: {parsed.strftime('%d %b %H:%M')}")
        if latest:
            self.refresh_time_label.configure(text=f"Last successful dashboard refresh: {max(latest).strftime('%d %b %Y %H:%M')}")
        cached = self.result_repository.get_result("planning")
        if cached is not None:
            payload = cached.payload
            count = int(payload.get("count") or 0)
            widgets = self.card_widgets["planning"]
            widgets["count"].configure(text=f"{count} results")
            widgets["status"].configure(
                text="Completed — cached Planning data available",
                text_color=SUCCESS,
            )
        for key in ("police", "fire", "sport", "council"):
            cached_feed = self.result_repository.get_result(key)
            if cached_feed is None:
                continue
            count = len(cached_feed.payload.get("stories") or [])
            widgets = self.card_widgets[key]
            widgets["count"].configure(text=f"{count} stories")
            widgets["status"].configure(text="Completed — saved feed available", text_color=SUCCESS)
            widgets["updated"].configure(text=f"Last updated: {cached_feed.completed_at.astimezone().strftime('%d %b %H:%M')}")

    def _updates_label(self, count, updates_date, tracking_started_at):
        today = datetime.now().astimezone().date()
        try:
            tracking_start = datetime.fromisoformat(tracking_started_at).astimezone()
        except (TypeError, ValueError):
            tracking_start = None
        if tracking_start and tracking_start.date() == today:
            noun = "item" if int(count or 0) == 1 else "items"
            return f"{int(count or 0)} new {noun} since {tracking_start.strftime('%H:%M')}"
        return self.coordinator.format_updates_today(count)

    def _render_recent_runs(self):
        for child in self.recent_runs_frame.winfo_children():
            child.destroy()
        runs = (self.state_store.load().get("recent_runs") or [])[:5]
        if not runs:
            ctk.CTkLabel(self.recent_runs_frame, text="No dashboard refreshes recorded yet.", text_color=TEXT_MUTED, anchor="w").pack(fill="x")
        for run in runs:
            timestamp = datetime.fromisoformat(run["timestamp"]).astimezone().strftime("%d %b %H:%M")
            values = "   ".join(f"{key.title()} {run.get(key, '—')}" for key in (*MODULE_KEYS, "events", "content", "government"))
            ctk.CTkLabel(self.recent_runs_frame, text=f"{timestamp}   {values}   {run.get('status', '').title()}", font=("Arial", 11), text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", pady=2)

    def _open_module(self, key):
        if key == "planning":
            started = perf_counter()
            self._open_planning_destination()
            self._record_window_open(key, perf_counter() - started)
            return
        existing = self.module_windows.get(key)
        if focus_existing_window(existing):
            return
        opener = {
            "planning": PlanningWindow,
            "police": lambda: open_police(self.master),
            "fire": lambda: open_fire(self.master),
            "sport": lambda: open_sport(self.master),
            "council": lambda: open_council(self.master),
        }[key]
        started = perf_counter()
        module = opener()
        track_window_reference(self.module_windows, key, module)
        module.dashboard_result_callback = (
            lambda payload, module_key=key: self.master.after(
                0, lambda: self._module_payload_updated(module_key, payload)
            )
        )
        stored = self.result_repository.get_result(key)
        if stored is not None:
            self._load_module_payload(key, module, stored.payload)
        self._record_window_open(key, perf_counter() - started)

    def _record_window_open(self, key, duration):
        state = self.state_store.load()
        module_state = state.setdefault("modules", {}).setdefault(key, {})
        module_state["last_window_open_seconds"] = round(float(duration), 3)
        module_state["last_window_open_at"] = datetime.now().astimezone().isoformat()
        self.state_store.save(state)

    def _open_system_health(self):
        """Open local operational health without starting collection."""

        from newsdesk.health.service import SystemHealthService
        service = SystemHealthService(
            dashboard_state=self.state_store,
            repository=self.result_repository,
            planning_cache=self.planning_cache,
            coordinator=self.coordinator,
            runtime=self,
        )
        window = open_system_health(
            self.master, service=service,
        )
        if self.module_windows.get("system_health") is not window:
            track_window_reference(self.module_windows, "system_health", window)

    def _open_data_retention(self):
        """Open the policy, schedule and auditable manual cleanup controls."""
        window = open_data_retention(self.master)
        if self.module_windows.get("data_retention") is not window:
            track_window_reference(self.module_windows, "data_retention", window)

    def _open_planning_destination(self):
        stored = self.result_repository.get_result("planning")
        if self._planning_open_target() == "results":
            existing = self.planning_results_window
            try:
                if existing and existing.window.winfo_exists():
                    existing.load_results(stored.payload["report_data"])
                    return
            except Exception:
                self.planning_results_window = None
            downloader_report = getattr(self.planning_downloader_window, "report_window", None)
            try:
                if downloader_report and downloader_report.window.winfo_exists():
                    downloader_report.load_results(stored.payload["report_data"])
                    self.planning_results_window = downloader_report
                    return
            except Exception:
                pass
            self.planning_results_window = open_planning_report(
                self.master,
                stored.payload["report_data"],
                refresh_command=self._refresh_planning_in_report,
            )
            return
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Planning results unavailable",
            "The previous Planning count is available, but its results payload is missing or invalid.\n\nOpen the Planning downloader to refresh or troubleshoot?",
            parent=self.master,
        ):
            return
        self._open_planning_downloader()

    def _open_planning_downloader(self):
        """Open or foreground only the Planning collection window."""
        existing = self.planning_downloader_window
        try:
            if existing and existing.window.winfo_exists():
                existing.show_downloader()
                return existing
        except Exception:
            self.planning_downloader_window = None
        self.planning_downloader_window = PlanningWindow(self.master)
        self.planning_downloader_window.dashboard_result_callback = (
            lambda payload: self.master.after(
                0, lambda: self._module_payload_updated("planning", payload)
            )
        )
        stored = self.result_repository.get_result("planning")
        if stored and stored.payload.get("report_data"):
            self.planning_downloader_window.load_results(
                stored.payload["report_data"]
            )
        return self.planning_downloader_window

    def _refresh_planning_in_report(self, report_window):
        """Start Planning-only collection with progress shown in the report."""
        existing = self.planning_downloader_window
        try:
            if not (existing and existing.window.winfo_exists()):
                existing = None
        except Exception:
            existing = None
        if existing is None:
            existing = PlanningWindow(
                self.master,
                visible=False,
                auto_open_report=False,
            )
            self.planning_downloader_window = existing
            existing.dashboard_result_callback = (
                lambda payload: self.master.after(
                    0, lambda: self._module_payload_updated("planning", payload)
                )
            )
        return existing.begin_background_refresh(report_window)

    def _planning_open_target(self):
        stored = self.result_repository.get_result("planning")
        if stored is not None and stored.payload.get("report_data"):
            return "results"
        return "downloader"

    def _load_module_payload(self, key, module, payload):
        if key == "planning":
            module.load_results(payload.get("report_data"))
            return
        arguments = [
            payload.get("stories") or [],
            payload.get("publish_results") or {},
            payload.get("errors") or [],
        ]
        if key == "council":
            arguments.append(payload.get("source_health") or {})
        module.load_stories(*arguments)

    def _module_payload_updated(self, key, payload):
        completed = datetime.now().astimezone()
        count = int(payload.get("count") or len(payload.get("stories") or []))
        self.result_repository.set_result(key, payload, completed)
        if key == "planning":
            try:
                self.planning_cache.save(payload["report_data"], completed)
            except Exception:
                LOGGER.exception("Could not persist manually refreshed Planning payload")
        from newsdesk.dashboard.models import DashboardRefreshResult
        result = DashboardRefreshResult(
            key, MODULE_NAMES[key], count=count, started_at=completed,
            completed_at=completed, success=True,
            item_keys=self.coordinator.item_keys(key, payload),
            updates_date=completed.date().isoformat(),
        )
        self.coordinator.record_result(result)
        self._update_card(result, load_open_module=False)
        self._reschedule()

    def _last_successful_times(self):
        state = self.state_store.load()
        output = {}
        for key in (*MODULE_KEYS, "government", "events", "content"):
            raw = (state.get("modules") or {}).get(key, {}).get("last_successful_refresh")
            try:
                output[key] = datetime.fromisoformat(raw) if raw else None
            except (TypeError, ValueError):
                output[key] = None
        cached = self.result_repository.get_result("planning")
        if cached is not None:
            output["planning"] = cached.completed_at
        return output

    def _hydrate_planning_cache(self):
        cached = self.planning_cache.load()
        if cached is None:
            return
        self.result_repository.set_result(
            "planning",
            {"report_data": cached.report_data, "count": cached.count},
            cached.completed_at,
        )

    def _assess_startup_freshness(self):
        now = datetime.now().astimezone()
        policies = self.state_store.load()["scheduler"]["module_policies"]
        last_times = self._last_successful_times()
        for key in ("government", "fire", "council", "police", "sport", "planning", "events", "content"):
            policy = policies[key]
            if key == "planning":
                last = last_times.get(key)
                if last and last.astimezone().date() == now.date():
                    self.card_widgets[key]["change"].configure(text="Already refreshed today")
                    self.card_widgets[key]["status"].configure(
                        text="Previous-session count — payload unavailable", text_color=WARNING
                    )
            stale = DashboardScheduler.startup_refresh_required(
                key, now, last_times.get(key), policy,
                self.result_repository.has_result(key),
            )
            if stale:
                self._start_refresh(key)
        self._reschedule()

    def _reschedule(self):
        if self.scheduler_after_id:
            self.master.after_cancel(self.scheduler_after_id)
            self.scheduler_after_id = None
        settings = self.state_store.load()["scheduler"]
        now = datetime.now().astimezone()
        runs = DashboardScheduler.module_next_runs(
            now, settings["module_policies"], self._last_successful_times()
        )
        for key, value in tuple(runs.items()):
            if value is not None and value <= now and self.coordinator.is_running(key):
                runs[key] = now.replace(microsecond=0) + timedelta(seconds=30)
        due = [(value, key) for key, value in runs.items() if value is not None]
        if due:
            self.next_refresh_at, next_key = min(due)
            self.next_refresh_label.configure(
                text=f"Next scheduled refresh: {MODULE_NAMES[next_key].split()[0]} {self.next_refresh_at.strftime('%H:%M')}"
            )
            delay = max(1000, int((self.next_refresh_at - now).total_seconds() * 1000))
            self.scheduler_after_id = self.master.after(delay, self._scheduled_refresh)
        else:
            self.next_refresh_at = None
            self.next_refresh_label.configure(text="Next scheduled refresh: Off")

    def _scheduled_refresh(self):
        now = datetime.now().astimezone()
        settings = self.state_store.load()["scheduler"]
        last_times = self._last_successful_times()
        for key, policy in settings["module_policies"].items():
            next_run = DashboardScheduler.next_module_run(
                key, now, last_times.get(key), policy
            )
            if next_run is None or next_run > now:
                continue
            window_key = f"{key}:{DashboardScheduler.scheduled_minute_key(now)}"
            if window_key in self.last_scheduled_windows:
                continue
            self.last_scheduled_windows.add(window_key)
            self._start_refresh(key)
        self.last_scheduled_windows = {
            value for value in self.last_scheduled_windows
            if value.endswith(now.strftime("%Y-%m-%dT%H:%M"))
        }
        self._reschedule()

    def _schedule_clock(self):
        now = datetime.now().astimezone()
        self.clock_label.configure(text=now.strftime("%A %d %B %Y  %H:%M:%S"))
        self.clock_after_id = self.master.after(1000, self._schedule_clock)

    def _open_scheduler_settings(self):
        dialog = ctk.CTkToplevel(self.master)
        dialog.title("NewsDesk Pro scheduler settings")
        dialog.geometry("640x760")
        dialog.transient(self.master)
        dialog.grab_set()
        settings = self.state_store.load()["scheduler"]
        ctk.CTkLabel(dialog, text="Automatic refresh", font=("Arial", 20, "bold")).pack(pady=(22, 8))
        startup = ctk.BooleanVar(value=bool(settings.get("refresh_on_startup", True)))
        ctk.CTkCheckBox(dialog, text="Refresh on application startup", variable=startup).pack(anchor="w", padx=35, pady=8)
        policies = settings["module_policies"]
        controls = ctk.CTkFrame(dialog, fg_color="transparent")
        controls.pack(fill="x", padx=35, pady=8)
        menus = {}
        settings_order=(*MODULE_KEYS, "events", "content", "government")
        for row, key in enumerate(settings_order):
            ctk.CTkLabel(controls, text=MODULE_NAMES[key], width=175, anchor="w").grid(row=row, column=0, sticky="w", pady=6)
            menu = ctk.CTkOptionMenu(controls, values=list(POLICY_OPTIONS[key]), width=180)
            menu.set(policies[key]["mode"])
            menu.grid(row=row, column=1, padx=8, pady=6)
            menus[key] = menu
        planning_row = len(settings_order)
        ctk.CTkLabel(controls, text="Planning preferred time", width=175, anchor="w").grid(row=planning_row, column=0, sticky="w", pady=6)
        daily_time = ctk.CTkEntry(controls, width=90)
        daily_time.insert(0, policies["planning"].get("daily_time", "06:15"))
        daily_time.grid(row=planning_row, column=1, sticky="w", padx=8, pady=6)
        heavy_row=planning_row+1
        ctk.CTkLabel(controls, text="Maximum heavy collectors", width=175, anchor="w").grid(row=heavy_row, column=0, sticky="w", pady=6)
        heavy_limit_menu = ctk.CTkOptionMenu(
            controls, values=["1", "2", "3"], width=90
        )
        heavy_limit_menu.set(str(settings.get("max_heavy_collectors", 2)))
        heavy_limit_menu.grid(row=heavy_row, column=1, sticky="w", padx=8, pady=6)
        error = ctk.CTkLabel(dialog, text="", text_color=ACCENT)
        error.pack()
        def save_settings():
            preferred = daily_time.get().strip()
            if not DashboardScheduler.validate_fixed_time(preferred):
                error.configure(text="Planning time must use 24-hour HH:MM, for example 06:15.")
                return
            for key, menu in menus.items():
                self.state["scheduler"]["module_policies"][key]["mode"] = menu.get()
            self.state["scheduler"]["module_policies"]["planning"]["daily_time"] = preferred
            self.state["scheduler"]["refresh_on_startup"] = startup.get()
            self.state["scheduler"]["max_heavy_collectors"] = int(
                heavy_limit_menu.get()
            )
            self.state_store.save(self.state)
            self._reschedule()
            dialog.destroy()
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(pady=12)
        ctk.CTkButton(buttons, text="Save settings", command=save_settings).pack(side="left", padx=6)
        ctk.CTkButton(
            buttons, text="CREATE DESKTOP SHORTCUT", fg_color=CARD_BG,
            border_width=1, border_color=BORDER,
            command=lambda: self._create_development_shortcut(dialog),
        ).pack(side="left", padx=6)

        now = datetime.now().astimezone()
        runs = DashboardScheduler.module_next_runs(
            now, policies, self._last_successful_times()
        )
        details = "   ".join(
            f"{MODULE_NAMES[key].split()[0]}: {value.strftime('%d %b %H:%M') if value else 'Off'}"
            for key, value in runs.items()
        )
        ctk.CTkLabel(
            dialog, text=f"Next runs\n{details}", wraplength=540,
            justify="left", text_color=TEXT_MUTED,
        ).pack(padx=35, pady=(6, 0))

    def _create_development_shortcut(self, parent):
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Create development shortcut",
            "Create or replace 'NewsDesk Pro (Development)' on your Desktop?\n\n"
            "This shortcut launches app.py with the installed Python interpreter.",
            parent=parent,
        ):
            return
        script = Path(__file__).resolve().parents[1] / "tools" / "install_newsdesk_shortcut.ps1"
        command = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-Development", "-Force",
            "-PythonPath", sys.executable,
            "-ProjectPath", str(Path(__file__).resolve().parents[1]),
        ]
        try:
            completed = subprocess.run(
                command, check=True, capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            messagebox.showinfo(
                "Shortcut created",
                completed.stdout.strip() or "Created NewsDesk Pro (Development) on the Desktop.",
                parent=parent,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", "") or str(error)
            messagebox.showerror(
                "Shortcut not created", str(detail).strip()[:300], parent=parent
            )

    def _on_close(self):
        active = any(not future.done() for future in self.futures.values())
        if active:
            from tkinter import messagebox
            if not messagebox.askyesno("Close NewsDesk Pro", "A refresh is still running. Close NewsDesk Pro and allow background cleanup to finish?"):
                return
        self._closing = True
        if self.scheduler_after_id:
            self.master.after_cancel(self.scheduler_after_id)
        if self.clock_after_id:
            self.master.after_cancel(self.clock_after_id)
        self.executor.shutdown(wait=False, cancel_futures=False)
        for value in tuple(self.module_windows.values()):
            try:
                close = getattr(value, "destroy", None) or getattr(getattr(value, "window", None), "destroy", None)
                if close:
                    close()
            except Exception:
                LOGGER.debug("Module cleanup failed", exc_info=True)
        self.master.destroy()
