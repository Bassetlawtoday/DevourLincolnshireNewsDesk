"""NewsDesk Pro Data Retention Centre."""

from __future__ import annotations

from pathlib import Path
import threading
import webbrowser

import customtkinter as ctk

from newsdesk.retention import AUDIT_PATH, POLICY_HTML, POLICY_VERSION, RETENTION_SCHEDULE, apply_retention, latest_audit, policy_text
from newsdesk.theme import ACTION_BLUE, ACTION_BLUE_HOVER
from newsdesk.ui_support import focus_existing_window


_window = None


class DataRetentionWindow(ctk.CTkToplevel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Data Retention Centre — NewsDesk Pro")
        self.geometry("1180x780")
        self.minsize(900, 650)
        self.configure(fg_color="#0f172a")
        self._build()
        self.refresh_status()
        self.transient(parent)
        self.after(50, self._bring_to_front)

    def _bring_to_front(self):
        """Present the centre above the dashboard without keeping it always-on-top."""
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(250, lambda: self.attributes("-topmost", False))

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="#111827", corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(header, text="DATA RETENTION CENTRE", font=("Arial", 26, "bold"), text_color="#f8fafc").pack(side="left", padx=24, pady=20)
        ctk.CTkButton(header, text="CLOSE", width=110, command=self.destroy).pack(side="right", padx=20)
        ctk.CTkButton(header, text="OPEN FORMAL POLICY", width=170, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.open_policy).pack(side="right", padx=6)
        self.run_button = ctk.CTkButton(header, text="RUN RETENTION NOW", width=170, fg_color="#dc2626", hover_color="#b91c1c", command=self.run_now)
        self.run_button.pack(side="right", padx=6)
        body = ctk.CTkScrollableFrame(self, fg_color="#0f172a")
        body.pack(fill="both", expand=True, padx=20, pady=18)
        self.status = ctk.CTkLabel(body, text="", anchor="w", justify="left", wraplength=1420, font=("Arial", 13, "bold"), text_color="#22c55e")
        self.status.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(body, text=f"Formal policy version {POLICY_VERSION}", anchor="w", font=("Arial", 16, "bold"), text_color="#f8fafc").pack(fill="x")
        ctk.CTkLabel(body, text=f"Policy: {POLICY_HTML}\nAudit trail: {AUDIT_PATH}", anchor="w", justify="left", text_color="#94a3b8").pack(fill="x", pady=(4, 14))
        schedule = "RETENTION SCHEDULE\n\n" + "\n".join(f"• {name}: {period}" for name, period in RETENTION_SCHEDULE)
        ctk.CTkLabel(body, text=schedule, anchor="w", justify="left", wraplength=1050, font=("Arial", 14), text_color="#cbd5e1").pack(fill="x", pady=(0, 16))
        self.policy = ctk.CTkTextbox(body, height=330, wrap="word", fg_color="#1f2937", text_color="#f8fafc")
        self.policy.pack(fill="both", expand=True)
        self.policy.insert("1.0", policy_text())
        self.policy.configure(state="disabled")

    def open_policy(self):
        webbrowser.open(POLICY_HTML.resolve().as_uri())

    def refresh_status(self):
        audit = latest_audit()
        if not audit:
            self.status.configure(text="No retention run has yet been recorded.", text_color="#f59e0b")
            return
        value = lambda key: int(audit.get(key, 0) or 0)
        details = (
            f"LDRS — emails removed: {value('emails_removed')}  •  articles minimised: {value('full_articles_minimised')}  •  metadata removed: {value('metadata_removed')}\n"
            f"Records — expired events removed: {value('expired_events_removed')}  •  planning records removed: {value('concluded_planning_removed')}\n"
            f"Files — logs removed: {value('old_logs_removed')}  •  cached images removed: {value('old_cached_images_removed')}"
        )
        self.status.configure(
            text=f"Last run: {audit.get('timestamp', 'Unknown')}  •  {audit.get('status', 'unknown').upper()}\n{details}",
            text_color="#22c55e" if audit.get("status") == "passed" else "#ef4444",
        )

    def run_now(self):
        self.run_button.configure(text="RUNNING…", state="disabled")
        def worker():
            apply_retention()
            self.after(0, lambda: (self.run_button.configure(text="RUN RETENTION NOW", state="normal"), self.refresh_status()))
        threading.Thread(target=worker, daemon=True).start()


def open_data_retention(parent=None):
    global _window
    if _window is not None and focus_existing_window(_window):
        return _window
    _window = DataRetentionWindow(parent)
    return _window
