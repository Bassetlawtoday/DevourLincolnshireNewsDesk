"""Read-oriented NewsDesk Pro System Health Centre."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
import os
from pathlib import Path

import customtkinter as ctk

from newsdesk.health.models import HealthStatus
from newsdesk.health.service import PROJECT_ROOT, SystemHealthService
from newsdesk.theme import (
    ACCENT, ACCENT_HOVER, APP_BG, BORDER, CARD_BG, HEADER_BG, ROUTINE,
    SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, URGENT,
)
from newsdesk.ui_support import (
    DEFAULT_SEARCH_DEBOUNCE_MS, DebouncedAction, IntelligenceWindowSupport,
    focus_existing_window, present_window_foreground,
)


LOGGER = logging.getLogger(__name__)
_active_window = None
FILTERS = ("All", "Failures", "Warnings", "Inactive", "Modules", "Scheduler", "Data and Cache", "Providers", "Configuration", "Documentation")
VISIBLE_ACTIONS = (
    ("RUN LOCAL DIAGNOSTICS", "_run_diagnostics"),
    ("COPY HEALTH SUMMARY", "_copy_summary"),
    ("COPY PERFORMANCE SUMMARY", "_copy_performance_summary"),
    ("EXPORT HEALTH REPORT", "_export_report"),
    ("OPEN LOG FOLDER", "_open_log_folder"),
    ("OPEN DATA FOLDER", "_open_data_folder"),
)
STATUS_COLOURS = {
    HealthStatus.HEALTHY: SUCCESS, HealthStatus.INACTIVE: TEXT_MUTED,
    HealthStatus.ATTENTION: ROUTINE, HealthStatus.DEGRADED: URGENT,
    HealthStatus.FAILED: ACCENT, HealthStatus.UNKNOWN: TEXT_MUTED,
}


def open_system_health(parent=None, *, service=None):
    global _active_window
    if focus_existing_window(_active_window):
        return _active_window
    _active_window = SystemHealthWindow(
        parent, service=service,
    )
    return _active_window


class SystemHealthWindow:
    def __init__(self, parent=None, *, service=None):
        self.parent = parent
        self.service = service or SystemHealthService()
        self.window = ctk.CTkToplevel(parent) if parent is not None else ctk.CTk()
        self.window.title("System Health — NewsDesk Pro")
        self.window.geometry("1400x860")
        self.window.minsize(1140, 720)
        self.window.configure(fg_color=APP_BG)
        self.lifecycle = IntelligenceWindowSupport(self.window, parent)
        self.lifecycle.install()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="system-health")
        self._refresh_future = None
        self._diagnostic_future = None
        self._feedback_after_id = None
        self.snapshot = None
        self.visible_items = []
        self.selected_item = None
        self._build()
        self._search_debounce = DebouncedAction(self.lifecycle, DEFAULT_SEARCH_DEBOUNCE_MS, self._render_items)
        self.refresh_health()
        present_window_foreground(
            self.window, temporary_topmost=True, maximized=True
        )
        self.window.bind("<Destroy>", self._on_destroy, add="+")

    def _build(self):
        self._build_header()
        body = ctk.CTkScrollableFrame(self.window, fg_color=APP_BG, corner_radius=0)
        body.pack(fill="both", expand=True)
        content = ctk.CTkFrame(body, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=22, pady=16)
        self._build_overview(content)
        self._build_workspace(content)
        self._build_actions(content)

    def _build_header(self):
        header = ctk.CTkFrame(self.window, fg_color=HEADER_BG, height=100, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = ctk.CTkFrame(header, fg_color="transparent")
        title.pack(side="left", padx=24, pady=15)
        ctk.CTkLabel(title, text="System Health", font=("Arial", 26, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(title, text="Operational status, diagnostics and platform readiness", text_color=TEXT_SECONDARY).pack(anchor="w")
        self.feedback_label = ctk.CTkLabel(title, text="Ready for local health checks.", font=("Arial", 11, "bold"), text_color=TEXT_MUTED, anchor="w")
        self.feedback_label.pack(anchor="w", pady=(2, 0))
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right", padx=24)
        self.refresh_button = ctk.CTkButton(actions, text="REFRESH HEALTH", width=145, command=self.refresh_health)
        self.refresh_button.pack(side="left", padx=5)
        ctk.CTkButton(actions, text="CLOSE", width=90, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self.close).pack(side="left", padx=5)

    def _build_overview(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        self.summary_cards = {}
        for key, title in (("overall", "SYSTEM STATUS"), ("Modules", "MODULES"), ("Scheduler", "SCHEDULER"), ("Data and Cache", "DATA AND CACHE"), ("Providers", "PROVIDERS")):
            card = ctk.CTkFrame(row, height=125, fg_color=CARD_BG, border_width=1, border_color=BORDER, corner_radius=12)
            card.pack(side="left", fill="both", expand=True, padx=4)
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=title, font=("Arial", 11, "bold"), text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=13, pady=(12, 4))
            status = ctk.CTkLabel(card, text="CHECKING", font=("Arial", 16, "bold"), text_color=TEXT_MUTED, anchor="w")
            status.pack(fill="x", padx=13)
            detail = ctk.CTkLabel(card, text="Local probes pending", font=("Arial", 10), text_color=TEXT_MUTED, justify="left", anchor="nw", wraplength=230)
            detail.pack(fill="both", expand=True, padx=13, pady=(3, 10))
            self.summary_cards[key] = (status, detail)

    def _build_workspace(self, parent):
        workspace = ctk.CTkFrame(parent, fg_color="transparent")
        workspace.pack(fill="both", expand=True, pady=(12, 0))
        workspace.grid_columnconfigure(0, weight=3)
        workspace.grid_columnconfigure(1, weight=2)
        left = ctk.CTkFrame(workspace, fg_color=HEADER_BG, border_width=1, border_color=BORDER, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 6))
        ctk.CTkLabel(left, text="HEALTH ITEMS", font=("Arial", 14, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=13, pady=(11, 6))
        controls = ctk.CTkFrame(left, fg_color="transparent")
        controls.pack(fill="x", padx=11, pady=(0, 7))
        self.search = ctk.CTkEntry(controls, placeholder_text="Search health items…", width=280)
        self.search.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.search.bind("<KeyRelease>", lambda _event: self._search_debounce.schedule())
        self.filter_menu = ctk.CTkOptionMenu(controls, values=list(FILTERS), width=170, command=lambda _value: self._render_items())
        self.filter_menu.pack(side="left")
        self.item_count = ctk.CTkLabel(left, text="0 items", text_color=TEXT_MUTED, anchor="e")
        self.item_count.pack(fill="x", padx=13)
        self.item_list = ctk.CTkScrollableFrame(left, fg_color=CARD_BG, height=350)
        self.item_list.pack(fill="both", expand=True, padx=11, pady=(5, 11))

        right = ctk.CTkFrame(workspace, fg_color=HEADER_BG, border_width=1, border_color=BORDER, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 4))
        ctk.CTkLabel(right, text="HEALTH DETAIL", font=("Arial", 14, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=13, pady=(11, 6))
        self.detail = ctk.CTkScrollableFrame(right, fg_color=CARD_BG, height=400)
        self.detail.pack(fill="both", expand=True, padx=11, pady=(0, 11))

    def _build_actions(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=HEADER_BG, border_width=1, border_color=BORDER, corner_radius=12)
        panel.pack(fill="x", padx=4, pady=(12, 0))
        ctk.CTkLabel(panel, text="LOCAL DIAGNOSTICS AND SAFE ACTIONS", font=("Arial", 13, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=13, pady=(11, 5))
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=10)
        for column in range(3):
            row.grid_columnconfigure(column, weight=1, uniform="health-actions")
        for index, (label, method_name) in enumerate(VISIBLE_ACTIONS):
            command = getattr(self, method_name)
            button = ctk.CTkButton(row, text=label, height=32, command=command)
            button.grid(row=index // 3, column=index % 3, sticky="ew", padx=3, pady=3)
            if label == "RUN LOCAL DIAGNOSTICS": self.diagnostics_button = button
        self.diagnostic_result = ctk.CTkLabel(panel, text="No local diagnostics run in this session.", text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=1280)
        self.diagnostic_result.pack(fill="x", padx=13, pady=(7, 4))
        self.history_text = ctk.CTkLabel(panel, text="", text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=1280)
        self.history_text.pack(fill="x", padx=13, pady=(0, 10))

    def refresh_health(self):
        """Assemble a local snapshot in a worker while preserving the last valid one."""

        if self._refresh_future and not self._refresh_future.done():
            return
        self._set_button_state(self.refresh_button, False)
        self._show_feedback("Refreshing health...", "progress")
        self._refresh_future = self.executor.submit(self.service.snapshot)
        self._poll_refresh()

    def _poll_refresh(self):
        if not self._refresh_future.done():
            self.lifecycle.call_later(80, self._poll_refresh)
            return
        self._set_button_state(self.refresh_button, True)
        try:
            snapshot = self._refresh_future.result()
        except Exception as error:
            LOGGER.exception("System Health local refresh failed")
            self._show_feedback("Health refresh failed; the previous snapshot has been preserved.", "error", clear_after=0)
            return
        self.snapshot = snapshot
        self._render_overview()
        self._render_items()
        self._render_history()
        self._show_feedback("Health refreshed successfully.", "success")

    def _render_overview(self):
        overall = self.snapshot.overall_status
        overall_label = "ATTENTION REQUIRED" if overall in {HealthStatus.ATTENTION, HealthStatus.DEGRADED, HealthStatus.FAILED} else "HEALTHY"
        self.summary_cards["overall"][0].configure(text=overall_label, text_color=STATUS_COLOURS[overall])
        self.summary_cards["overall"][1].configure(text=f"{self.snapshot.warning_count} warnings • {self.snapshot.failure_count} failures • {self.snapshot.inactive_count} inactive\nChecked {self.snapshot.completed_at.astimezone().strftime('%d %b %H:%M:%S')}")
        for category in ("Modules", "Scheduler", "Data and Cache", "Providers"):
            counts = self.snapshot.categories.get(category, {})
            category_items = [item for item in self.snapshot.items if item.category == category]
            status = max(category_items, key=lambda item: {HealthStatus.FAILED: 5, HealthStatus.DEGRADED: 4, HealthStatus.ATTENTION: 3, HealthStatus.HEALTHY: 2, HealthStatus.UNKNOWN: 1, HealthStatus.INACTIVE: 0}[item.status]).status if category_items else HealthStatus.UNKNOWN
            self.summary_cards[category][0].configure(text=status.value, text_color=STATUS_COLOURS[status])
            self.summary_cards[category][1].configure(text=f"Healthy {counts.get('HEALTHY', 0)} • Attention {counts.get('ATTENTION', 0) + counts.get('DEGRADED', 0)}\nFailed {counts.get('FAILED', 0)} • Inactive {counts.get('INACTIVE', 0)}")

    def _render_items(self):
        if not self.snapshot:
            return
        selected_key = self.selected_item.key if self.selected_item else ""
        self.visible_items = self.service.filter_items(self.snapshot, search=self.search.get(), filter_name=self.filter_menu.get())
        for child in self.item_list.winfo_children(): child.destroy()
        for item in self.visible_items:
            card = ctk.CTkButton(self.item_list, text=f"{item.status.value}  •  {item.category}\n{item.display_name}\n{item.summary}", anchor="w", height=66, fg_color="#263449" if item.key == selected_key else HEADER_BG, border_width=1, border_color=STATUS_COLOURS[item.status], command=lambda value=item: self._select_item(value))
            card.pack(fill="x", pady=3)
        self.item_count.configure(text=f"{len(self.visible_items)} of {len(self.snapshot.items)} items")
        match = next((item for item in self.visible_items if item.key == selected_key), None)
        self._select_item(match or (self.visible_items[0] if self.visible_items else None))

    def _select_item(self, item):
        self.selected_item = item
        for child in self.detail.winfo_children(): child.destroy()
        if item is None:
            ctk.CTkLabel(self.detail, text="No health items match the current search and filter.", text_color=TEXT_MUTED).pack(padx=8, pady=15)
            return
        self._detail_heading(item.status.value, STATUS_COLOURS[item.status])
        self._detail_row("Name", item.display_name)
        self._detail_row("Category", item.category)
        self._detail_row("Summary", item.summary)
        self._detail_row("Authoritative Source", item.source or "Not available")
        self._detail_row("Checked", item.checked_at.astimezone().isoformat(timespec="seconds"))
        self._detail_row("Latest Success", item.last_success.astimezone().isoformat(timespec="seconds") if item.last_success else "Unknown")
        self._detail_row("Latest Failure", item.last_failure.astimezone().isoformat(timespec="seconds") if item.last_failure else "None")
        self._detail_row("Recommended Action", item.recommended_action)
        self._detail_row("Related Path", item.related_path or "Not available")
        self._detail_heading("SAFE DETAILS", TEXT_SECONDARY)
        for key, value in item.details.items():
            self._detail_row(str(key).replace("_", " ").title(), json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else value)

    def _detail_heading(self, text, colour):
        ctk.CTkLabel(self.detail, text=text, font=("Arial", 13, "bold"), text_color=colour, anchor="w").pack(fill="x", padx=8, pady=(10, 4))

    def _detail_row(self, label, value):
        row = ctk.CTkFrame(self.detail, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(row, text=label, width=135, font=("Arial", 10, "bold"), text_color=TEXT_MUTED, anchor="w").pack(side="left", anchor="n")
        ctk.CTkLabel(row, text=str(value), text_color=TEXT_PRIMARY, anchor="w", justify="left", wraplength=360).pack(side="left", fill="x", expand=True)

    def _run_diagnostics(self):
        if self._diagnostic_future and not self._diagnostic_future.done():
            return
        self._set_button_state(self.diagnostics_button, False)
        self._show_feedback("Running local diagnostics...", "progress")
        self.diagnostic_result.configure(text="Local diagnostics running…", text_color=TEXT_SECONDARY)
        self._diagnostic_future = self.executor.submit(self.service.run_local_diagnostics)
        self._poll_diagnostics()

    def _poll_diagnostics(self):
        if not self._diagnostic_future.done():
            self.lifecycle.call_later(80, self._poll_diagnostics)
            return
        self._set_button_state(self.diagnostics_button, True)
        try:
            result = self._diagnostic_future.result()
            text = (
                f"Local diagnostics {result['status'].casefold()} in {result['duration']:.2f}s • "
                f"{result['checks_passed']} of {result['checks_total']} checks completed • "
                f"Configuration {result['configuration']['status']} • Database {result['database']['status']} • "
                f"Documentation {result['documentation']['status']}"
            )
            colour = SUCCESS if result["status"] == "Passed" else ROUTINE
            self.diagnostic_result.configure(text=text, text_color=colour)
            if result["status"] == "Passed":
                self._show_feedback("Local diagnostics completed successfully.", "success")
            else:
                failing = "; ".join(result.get("errors") or ())
                self._show_feedback(f"Local diagnostics completed partially: {failing}"[:300], "warning", clear_after=0)
        except Exception:
            LOGGER.exception("System Health diagnostics failed")
            self.diagnostic_result.configure(text="Local diagnostics failed. The latest health snapshot remains available.", text_color=ACCENT)
            self._show_feedback("Local diagnostics failed.", "error", clear_after=0)

    def _copy_summary(self):
        if not self.snapshot:
            self._show_feedback("Health summary is unavailable until the first refresh completes.", "warning")
            return
        try:
            summary = self.service.copy_summary(self.snapshot)
            self.window.clipboard_clear()
            self.window.clipboard_append(summary)
            self.window.update_idletasks()
        except Exception:
            LOGGER.exception("Could not copy the health summary")
            self._show_feedback("Could not copy the health summary.", "error", clear_after=0)
            return
        self._show_feedback("Health summary copied to clipboard.", "success")

    def _copy_performance_summary(self):
        try:
            summary = self.service.performance_summary()
            self.window.clipboard_clear()
            self.window.clipboard_append(summary)
            self.window.update_idletasks()
        except Exception:
            LOGGER.exception("Could not copy the performance summary")
            self._show_feedback(
                "Could not copy the performance summary.", "error", clear_after=0
            )
            return
        self._show_feedback("Performance summary copied to clipboard.", "success")

    def _export_report(self):
        if not self.snapshot:
            self._show_feedback("Health report is unavailable until the first refresh completes.", "warning")
            return
        try:
            path = self.service.export_report(self.snapshot)
            self._show_feedback(f"Health report exported to: {path.resolve()}", "success", clear_after=10000)
        except Exception:
            LOGGER.exception("Health report could not be exported")
            self._show_feedback("Health report could not be exported.", "error", clear_after=0)

    def _open_folder(self, path):
        path = Path(path).resolve()
        label = "log" if path.name.casefold() == "logs" else "data"
        if not path.exists():
            message = "Log folder is not configured or does not exist." if label == "log" else "Data folder is unavailable."
            self._show_feedback(message, "warning", clear_after=0)
            return
        try:
            os.startfile(path)
        except (OSError, AttributeError):
            LOGGER.exception("Could not open %s folder", label)
            self._show_feedback(f"{label.title()} folder could not be opened.", "error", clear_after=0)
            return
        self._show_feedback(f"Opened {label} folder.", "success")

    def _open_log_folder(self):
        self._open_folder(PROJECT_ROOT / "logs")

    def _open_data_folder(self):
        self._open_folder(PROJECT_ROOT / "data")

    def _show_feedback(self, message, kind="info", *, clear_after=5000):
        if self._feedback_after_id is not None:
            self.lifecycle.cancel(self._feedback_after_id)
            self._feedback_after_id = None
        colours = {"progress": TEXT_SECONDARY, "success": SUCCESS, "warning": ROUTINE, "error": ACCENT, "info": TEXT_MUTED}
        self.feedback_label.configure(text=message, text_color=colours.get(kind, TEXT_MUTED))
        if clear_after:
            self._feedback_after_id = self.lifecycle.call_later(clear_after, self._clear_feedback)

    def _clear_feedback(self):
        self._feedback_after_id = None
        self.feedback_label.configure(text="Ready for local health checks.", text_color=TEXT_MUTED)

    @staticmethod
    def _set_button_state(button, enabled):
        if enabled:
            button.configure(state="normal", fg_color="#2563eb", hover_color="#1d4ed8", text_color=TEXT_PRIMARY)
        else:
            button.configure(state="disabled", fg_color="#162033", hover_color="#162033", text_color_disabled="#64748b")

    def _render_history(self):
        history = self.service.recent_history(5)
        lines = []
        for value in history:
            try: shown = datetime.fromisoformat(value["checked_at"]).astimezone().strftime("%H:%M")
            except (KeyError, ValueError, TypeError): shown = "Unknown"
            lines.append(f"{shown} {value.get('overall_status', 'UNKNOWN').title()} with {value.get('warning_count', 0)} warning(s)")
        self.history_text.configure(text="LAST 5 CHECKS  " + ("   •   ".join(lines) if lines else "No prior checks"))

    def close(self):
        if self._feedback_after_id is not None:
            self.lifecycle.cancel(self._feedback_after_id)
            self._feedback_after_id = None
        self._search_debounce.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.lifecycle.close()

    def _on_destroy(self, event):
        global _active_window
        if event.widget is self.window:
            self.executor.shutdown(wait=False, cancel_futures=True)
            if _active_window is self: _active_window = None
