import customtkinter as ctk
from datetime import date
from html import escape
from tkinter import messagebox, ttk
import webbrowser
from PIL import Image
from editorial.story_window import open_story_desk
from newsdesk.header import NewsDeskHeader
from newsdesk.newsletter.selection import planning_story
from newsdesk.social.selection import add_story_to_social_desk, social_workflow_status
from modules.planning_source_manager import SourceManagerWindow
from newsdesk.ui_support import (
    focus_existing_window,
    present_window_foreground,
)
from newsdesk.theme import HEADER_HEIGHT

APP_BG = "#0f172a"
HEADER_BG = "#111827"
PANEL_BG = "#172033"
CARD_BG = "#1f2937"
MUTED_BG = "#263743"
BRAND_RED = "#ed3b35"
BRAND_RED_HOVER = "#d6312c"
ACTION_BLUE = "#2563eb"
ACTION_BLUE_HOVER = "#1d4ed8"
PRIMARY = BRAND_RED
PRIMARY_DARK = BRAND_RED_HOVER
GOLD = "#eab308"
TEXT = "#f8fafc"
MUTED_TEXT = "#94a3b8"
BORDER = "#334155"
ENTRY_BG = "#111827"


class PlanningReportWindow:
    """Displays the Version 2.2 Stage 3 planning editorial dashboard."""

    def __init__(self, parent, report_data, refresh_command=None):
        self.parent = parent
        self.refresh_command = refresh_command
        self.report_data = report_data or {}
        self.all_applications = self.report_data.get("all_applications", [])
        self.filtered_applications = list(self.all_applications)

        self.window = ctk.CTkToplevel(parent)
        self.window.withdraw()
        self.window.title("Planning Intelligence Dashboard")
        self.window.geometry("1450x900")
        self.window.minsize(1100, 720)
        self.window.configure(fg_color=APP_BG)

        self.window.transient(parent)

        self.search_var = ctk.StringVar()
        self.register_count_label = None
        self.register_textbox = None
        self.copy_status_label = None
        self.source_manager_window = None
        self.refresh_worker = None
        self.refresh_status_label = None
        self.refresh_current_label = None
        self.refresh_elapsed_label = None
        self.refresh_progress = None
        self.refresh_log = None

        self.build()
        self.window.protocol("WM_DELETE_WINDOW", self._close_window)
        self.window.after_idle(
            lambda: present_window_foreground(
                self.window,
                temporary_topmost=True,
                maximized=True,
            )
        )

    def build(self):
        self._build_header()
        self._build_refresh_monitor()

        content = ctk.CTkScrollableFrame(
            self.window,
            fg_color=APP_BG,
            corner_radius=0,
            scrollbar_button_color="#475569",
            scrollbar_button_hover_color="#64748b",
        )
        content.pack(fill="both", expand=True, padx=18, pady=(14, 12))

        self._build_story_of_week(content)
        self._build_summary(content)
        self._build_source_status(content)
        self._build_intelligence_grid(content)
        self._build_watchlist(content)
        self._build_top_stories(content)
        self._build_full_register(content)

        footer = ctk.CTkFrame(
            self.window,
            fg_color=HEADER_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        footer.pack(fill="x")

        ctk.CTkButton(
            footer,
            text="CLOSE",
            width=210,
            height=38,
            fg_color="#374151",
            hover_color="#475569",
            command=self._close_window,
        ).pack(pady=12)

    def _close_window(self):
        """Close only the report and safely return focus to its parent."""

        try:
            self.window.destroy()
        finally:
            try:
                if self.parent is not None and self.parent.winfo_exists():
                    self.parent.deiconify()
                    self.parent.lift()
                    self.parent.focus_force()
            except Exception:
                pass

    def load_results(self, report_data):
        """Rebuild this briefing from a completed, non-scraping payload."""

        if not isinstance(report_data, dict):
            return
        self.report_data = report_data
        self.all_applications = list(report_data.get("all_applications") or [])
        self.filtered_applications = list(self.all_applications)
        self.search_var.set("")
        for child in self.window.winfo_children():
            child.destroy()
        self.register_count_label = None
        self.register_textbox = None
        self.register_tree = None
        self.register_selected_application = None
        self.register_action_buttons = []
        self.copy_status_label = None
        self.build()

        present_window_foreground(
            self.window,
            temporary_topmost=True,
            maximized=True,
        )

    def _build_header(self):
        secondary_actions = []
        if callable(self.refresh_command):
            secondary_actions.append(
                ("REFRESH PLANNING DATA", self._open_planning_downloader)
            )
        secondary_actions.extend(
            (
                ("MANAGE SOURCES", self._open_source_manager),
                ("SOCIAL DESK", self._open_social_desk),
            )
        )
        self.header = NewsDeskHeader(
            self.window,
            module_title="Planning Intelligence",
            subtitle="Collect  •  Prioritise  •  Review  •  Publish",
            close_command=self._close_window,
            secondary_actions=tuple(secondary_actions),
            height=HEADER_HEIGHT,
        )
        self.header.pack(fill="x")

    def _open_planning_downloader(self):
        """Start collection and keep progress inside the briefing."""
        if not callable(self.refresh_command):
            return
        try:
            self.refresh_worker = self.refresh_command(self)
            self._poll_refresh_worker()
            return self.refresh_worker
        except Exception:
            raise

    def _build_refresh_monitor(self):
        source_rows = list(self.report_data.get("planning_sources") or [])
        has_saved_briefing = bool(self.all_applications or source_rows)
        current = int(self.report_data.get("planning_sources_current", 0) or 0)
        retained = int(self.report_data.get("planning_sources_retained", 0) or 0)
        failed = int(self.report_data.get("planning_sources_failed", 0) or 0)
        if has_saved_briefing:
            initial_status = (
                "Planning refresh: Complete"
                if not retained and not failed
                else "Planning refresh: Complete with source warnings"
            )
            initial_current = (
                f"Latest saved briefing: {current} current"
                f" • {retained} retained • {failed} unavailable"
            )
            initial_log = (
                "Latest completed Planning briefing loaded.\n"
                "Click REFRESH PLANNING DATA to collect new weekly lists.\n"
            )
        else:
            initial_status = "Planning refresh: Ready"
            initial_current = "Current: Waiting"
            initial_log = "Click REFRESH PLANNING DATA to collect the latest weekly lists.\n"
        panel = ctk.CTkFrame(
            self.window,
            fg_color=PANEL_BG,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        panel.pack(fill="x", padx=18, pady=(8, 0))
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 5))
        self.refresh_status_label = ctk.CTkLabel(
            row,
            text=initial_status,
            font=("Arial", 13, "bold"),
            text_color="#22c55e" if has_saved_briefing and not failed else TEXT,
        )
        self.refresh_status_label.pack(side="left")
        self.refresh_elapsed_label = ctk.CTkLabel(
            row, text="Elapsed: 00:00", text_color=MUTED_TEXT
        )
        self.refresh_elapsed_label.pack(side="right")
        self.refresh_current_label = ctk.CTkLabel(
            panel, text=initial_current, anchor="w", text_color="#cbd5e1"
        )
        self.refresh_current_label.pack(fill="x", padx=14)
        self.refresh_progress = ctk.CTkProgressBar(panel)
        self.refresh_progress.pack(fill="x", padx=14, pady=(6, 8))
        self.refresh_progress.set(1 if has_saved_briefing else 0)
        self.refresh_log = ctk.CTkTextbox(panel, height=90)
        self.refresh_log.pack(fill="x", padx=14, pady=(0, 10))
        self.refresh_log.insert("end", initial_log)
        self.refresh_log.configure(state="disabled")

    def _poll_refresh_worker(self):
        worker = self.refresh_worker
        if worker is None:
            return
        try:
            self.refresh_status_label.configure(text=worker.status.cget("text"))
            self.refresh_current_label.configure(text=worker.current_item.cget("text"))
            self.refresh_elapsed_label.configure(text=worker.elapsed.cget("text"))
            self.refresh_progress.set(float(worker.progress.get()))
            log_text = worker.log.get("1.0", "end").strip()
            self.refresh_log.configure(state="normal")
            self.refresh_log.delete("1.0", "end")
            self.refresh_log.insert("end", log_text)
            self.refresh_log.see("end")
            self.refresh_log.configure(state="disabled")
        except Exception:
            return
        if worker.running:
            self.window.after(500, self._poll_refresh_worker)

    def _open_source_manager(self):
        if focus_existing_window(self.source_manager_window):
            return
        self.source_manager_window = SourceManagerWindow(
            self.window,
            module_profile="planning",
            allow_custom_sources=False,
        )

    def _open_social_desk(self):
        from modules.social_desk import open_social_desk
        return open_social_desk(self.window)

    def _panel(self, parent, title, subtitle=None):
        panel = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        panel.pack(fill="x", pady=(0, 16))

        heading = ctk.CTkFrame(panel, fg_color="transparent")
        heading.pack(fill="x", padx=20, pady=(17, 8 if subtitle else 14))

        ctk.CTkLabel(
            heading,
            text=title,
            font=("Arial", 19, "bold"),
            text_color=TEXT,
            anchor="w",
        ).pack(fill="x")

        if subtitle:
            ctk.CTkLabel(
                panel,
                text=subtitle,
                font=("Arial", 12),
                text_color=MUTED_TEXT,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=20, pady=(0, 12))

        return panel

    def _priority_colour(self, priority):
        colours = {
            "FRONT PAGE": "#b13b32",
            "LEAD WEBSITE STORY": "#9a6500",
            "WEBSITE STORY": "#1769aa",
            "BRIEF MENTION": "#54717f",
            "ARCHIVE": "#68747d",
        }
        return colours.get(priority, PRIMARY)

    def _social_workflow_badge(self, parent, application):
        status = social_workflow_status(planning_story(application))
        if not status:
            return
        ctk.CTkLabel(
            parent,
            text=status,
            font=("Arial", 11, "bold"),
            text_color="#22c55e" if status == "SENT TO METRICOOL" else "#60a5fa",
            anchor="w",
        ).pack(anchor="w", padx=18, pady=(0, 5))

    def _tag_colour(self, tag):
        colours = {
            "Housing": "#2b7a3d",
            "Battery Storage": "#7a4aa3",
            "Renewable Energy": "#297f70",
            "Commercial": "#a45d24",
            "Heritage": "#7a5937",
            "Telecoms": "#356b9d",
            "Community": "#a34f6f",
            "Agriculture": "#61753c",
            "Trees": "#35765b",
            "Transport": "#596d7a",
            "Demolition": "#8a4f45",
            "Change of Use": "#6a5b92",
        }
        return colours.get(tag, "#60717d")

    def _build_story_of_week(self, parent):
        story = self.report_data.get("story_of_week")
        panel = self._panel(
            parent,
            "🏆 Story of the Week",
            "The strongest planning application selected by NewsDesk's editorial scoring.",
        )

        if not story:
            ctk.CTkLabel(
                panel,
                text="No application is available for Story of the Week.",
                font=("Arial", 14),
                text_color=MUTED_TEXT,
            ).pack(anchor="w", padx=20, pady=(0, 18))
            return

        card = ctk.CTkFrame(
            panel,
            fg_color=CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        card.pack(fill="x", padx=20, pady=(0, 20))

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))

        priority = story.get("editorial_priority", "WEBSITE STORY")
        priority_badge = ctk.CTkLabel(
            top,
            text=priority,
            font=("Arial", 13, "bold"),
            text_color="#ffffff",
            fg_color=self._priority_colour(priority),
            corner_radius=8,
            padx=12,
            pady=6,
        )
        priority_badge.pack(side="left")

        score = int(story.get("score", 0))
        stars = "★" * int(story.get("priority_stars", 1))
        ctk.CTkLabel(
            top,
            text=f"{stars}   NEWS VALUE {score}",
            font=("Arial", 16, "bold"),
            text_color=GOLD,
        ).pack(side="right")

        proposal = (
            story.get("proposal_summary")
            or story.get("proposal")
            or "Proposal details unavailable"
        )
        ctk.CTkLabel(
            card,
            text=proposal,
            font=("Arial", 21, "bold"),
            text_color=TEXT,
            justify="left",
            anchor="w",
            wraplength=1040,
        ).pack(fill="x", padx=18, pady=(4, 9))

        metadata = (
            f"📍 {story.get('area') or 'Unknown area'}    •    "
            f"{story.get('reference') or 'No reference'}"
        )
        ctk.CTkLabel(
            card,
            text=metadata,
            font=("Arial", 12, "bold"),
            text_color=MUTED_TEXT,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 9))

        self._social_workflow_badge(card, story)

        self._build_tags(card, story.get("tags", []), padx=18)

        divider = ctk.CTkFrame(card, height=1, fg_color=BORDER)
        divider.pack(fill="x", padx=18, pady=(12, 12))

        ctk.CTkLabel(
            card,
            text="WHY THIS MATTERS",
            font=("Arial", 12, "bold"),
            text_color=PRIMARY,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 6))

        for reason in story.get("why_news", []):
            ctk.CTkLabel(
                card,
                text=f"✓  {reason}",
                font=("Arial", 13),
                text_color=TEXT,
                justify="left",
                anchor="w",
                wraplength=1030,
            ).pack(fill="x", padx=22, pady=(0, 5))

        button_row = ctk.CTkFrame(card, fg_color="transparent")
        button_row.pack(fill="x", padx=18, pady=(10, 16))

        ctk.CTkButton(
            button_row,
            text="Generate Story",
            width=160,
            height=34,
            fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,
            command=lambda s=story: open_story_desk(self.window, s),
        ).pack(side="left")

        ctk.CTkButton(
            button_row,
            text="Add to Newsletter",
            width=170,
            height=34,
            fg_color=BRAND_RED,
            hover_color=BRAND_RED_HOVER,
            command=lambda s=story: self._add_planning_to_newsletter(s),
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            button_row,
            text="Add to Socials",
            width=160,
            height=34,
            fg_color=BRAND_RED,
            hover_color=BRAND_RED_HOVER,
            command=lambda s=story: self._add_planning_to_socials(s),
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            button_row,
            text="Open Source",
            width=140,
            height=34,
            fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,
            command=lambda s=story: self._open_planning_source(s),
        ).pack(side="left", padx=(8, 0))

    def _build_summary(self, parent):
        panel = self._panel(parent, "Weekly Intelligence")
        summary = self.report_data.get("editorial_summary", {})

        cards = (
            ("Applications", self.report_data.get("applications_processed", 0), "Downloaded this week"),
            ("Newsworthy", self.report_data.get("newsworthy_stories", 0), "Standalone story threshold"),
            ("Front Page", summary.get("front_page", self.report_data.get("front_page_candidates", 0)), "Highest priority"),
            ("Lead Stories", summary.get("lead_website", 0), "Strong website leads"),
            ("Website Stories", summary.get("website_story", 0), "Standard coverage"),
            ("Brief Mentions", summary.get("brief_mention", 0), "Round-up material"),
        )

        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=15, pady=(0, 18))
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="summary")

        for index, (label, value, note) in enumerate(cards):
            row, column = divmod(index, 3)
            card = ctk.CTkFrame(
                grid,
                fg_color=CARD_BG,
                corner_radius=10,
                border_width=1,
                border_color=BORDER,
            )
            card.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)

            ctk.CTkLabel(
                card,
                text=str(value),
                font=("Arial", 27, "bold"),
                text_color=PRIMARY,
            ).pack(pady=(12, 0))

            ctk.CTkLabel(
                card,
                text=label,
                font=("Arial", 13, "bold"),
                text_color=TEXT,
            ).pack(pady=(0, 2))

            ctk.CTkLabel(
                card,
                text=note,
                font=("Arial", 11),
                text_color=MUTED_TEXT,
            ).pack(pady=(0, 12))

        authority_rows = self.report_data.get("authority_breakdown", [])
        if authority_rows:
            ctk.CTkLabel(
                panel,
                text="Authority Activity",
                font=("Arial", 16, "bold"),
                text_color=TEXT,
                anchor="w",
            ).pack(fill="x", padx=20, pady=(2, 8))
            authority_grid = ctk.CTkFrame(panel, fg_color="transparent")
            authority_grid.pack(fill="x", padx=15, pady=(0, 18))
            authority_grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="authority")
            for index, row_data in enumerate(authority_rows):
                row, column = divmod(index, 3)
                item = ctk.CTkFrame(
                    authority_grid,
                    fg_color=CARD_BG,
                    corner_radius=8,
                    border_width=1,
                    border_color=BORDER,
                )
                item.grid(row=row, column=column, sticky="nsew", padx=5, pady=4)
                ctk.CTkLabel(
                    item,
                    text=str(row_data.get("count", 0)),
                    font=("Arial", 19, "bold"),
                    text_color=PRIMARY,
                ).pack(side="left", padx=(12, 9), pady=9)
                ctk.CTkLabel(
                    item,
                    text=str(row_data.get("name", "Planning authority")),
                    font=("Arial", 12, "bold"),
                    text_color=TEXT,
                    anchor="w",
                    wraplength=280,
                ).pack(side="left", fill="x", expand=True, padx=(0, 10), pady=9)

    def _build_intelligence_grid(self, parent):
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 16))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="intelligence")

        categories = ctk.CTkFrame(
            grid,
            fg_color=PANEL_BG,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        categories.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        areas = ctk.CTkFrame(
            grid,
            fg_color=PANEL_BG,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        areas.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        self._build_ranked_breakdown(
            categories,
            "Hot Topics",
            self.report_data.get("category_breakdown", []),
            8,
        )
        self._build_ranked_breakdown(
            areas,
            "Planning Hotspots",
            self.report_data.get("area_breakdown", []),
            8,
        )
        unavailable = int(self.report_data.get("unavailable_area_count", 0) or 0)
        if unavailable:
            ctk.CTkLabel(
                areas,
                text=f"Area unavailable for {unavailable} applications (excluded from ranking)",
                font=("Arial", 11),
                text_color=MUTED_TEXT,
                anchor="w",
            ).pack(fill="x", padx=18, pady=(0, 14))

    def _build_source_status(self, parent):
        rows = self.report_data.get("planning_sources", [])
        if not rows:
            return
        current = int(self.report_data.get("planning_sources_current", 0) or 0)
        retained = int(self.report_data.get("planning_sources_retained", 0) or 0)
        failed = int(self.report_data.get("planning_sources_failed", 0) or 0)
        panel = self._panel(
            parent,
            "Source Refresh Status",
            f"{current} current  •  {retained} retained from an earlier refresh  •  {failed} unavailable",
        )
        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=15, pady=(0, 18))
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="source_status")
        colours = {
            "Current": "#22c55e",
            "Empty": "#60a5fa",
            "Retained": "#f59e0b",
            "Failed": "#ef4444",
        }
        for index, source in enumerate(rows):
            row, column = divmod(index, 3)
            item = ctk.CTkFrame(
                grid,
                fg_color=CARD_BG,
                corner_radius=8,
                border_width=1,
                border_color=BORDER,
            )
            item.grid(row=row, column=column, sticky="nsew", padx=5, pady=4)
            status = str(source.get("status") or "Failed")
            ctk.CTkLabel(
                item,
                text=status.upper(),
                font=("Arial", 11, "bold"),
                text_color=colours.get(status, MUTED_TEXT),
                width=72,
            ).pack(side="left", padx=(10, 6), pady=9)
            ctk.CTkLabel(
                item,
                text=(
                    f"{source.get('name', 'Planning source')}\n"
                    f"{int(source.get('application_count', 0) or 0)} applications"
                ),
                font=("Arial", 11, "bold"),
                text_color=TEXT,
                anchor="w",
                justify="left",
                wraplength=270,
            ).pack(side="left", fill="x", expand=True, padx=(0, 10), pady=8)

    def _build_ranked_breakdown(self, parent, title, rows, limit):
        ctk.CTkLabel(
            parent,
            text=title,
            font=("Arial", 18, "bold"),
            text_color=TEXT,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 12))

        visible_rows = rows[:limit]

        if not visible_rows:
            ctk.CTkLabel(
                parent,
                text="No data available.",
                font=("Arial", 13),
                text_color=MUTED_TEXT,
            ).pack(anchor="w", padx=18, pady=(0, 18))
            return

        maximum = max(int(row.get("count", 0)) for row in visible_rows) or 1

        for position, row in enumerate(visible_rows, start=1):
            item = ctk.CTkFrame(parent, fg_color="transparent")
            item.pack(fill="x", padx=18, pady=(0, 10))

            line = ctk.CTkFrame(item, fg_color="transparent")
            line.pack(fill="x")

            name = row.get("name") or "Unknown"
            count = int(row.get("count", 0))

            ctk.CTkLabel(
                line,
                text=f"{position}. {name}",
                font=("Arial", 12, "bold"),
                text_color=TEXT,
                anchor="w",
            ).pack(side="left")

            right = ctk.CTkFrame(line, fg_color="transparent")
            right.pack(side="right")

            status = row.get("status")
            if status:
                ctk.CTkLabel(
                    right,
                    text=status,
                    font=("Arial", 10),
                    text_color=MUTED_TEXT,
                ).pack(side="left", padx=(0, 10))

            ctk.CTkLabel(
                right,
                text=str(count),
                font=("Arial", 12, "bold"),
                text_color=PRIMARY,
            ).pack(side="right")

            progress = ctk.CTkProgressBar(
                item,
                height=7,
                progress_color=PRIMARY,
                fg_color=MUTED_BG,
            )
            progress.pack(fill="x", pady=(4, 0))
            progress.set(count / maximum)

        ctk.CTkLabel(parent, text="", height=4).pack()

    def _build_watchlist(self, parent):
        panel = self._panel(
            parent,
            "Editor's Watchlist",
            "Themes automatically detected for possible follow-up or wider coverage.",
        )

        watchlist = self.report_data.get("watchlist", [])

        if not watchlist:
            ctk.CTkLabel(
                panel,
                text="No priority themes were detected in this download.",
                font=("Arial", 13),
                text_color=MUTED_TEXT,
            ).pack(anchor="w", padx=20, pady=(0, 18))
            return

        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=15, pady=(0, 18))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="watch")

        for index, item in enumerate(watchlist):
            row, column = divmod(index, 2)
            card = ctk.CTkFrame(
                grid,
                fg_color=CARD_BG,
                corner_radius=10,
                border_width=1,
                border_color=BORDER,
            )
            card.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)

            heading = ctk.CTkFrame(card, fg_color="transparent")
            heading.pack(fill="x", padx=14, pady=(12, 4))

            ctk.CTkLabel(
                heading,
                text=item.get("title", "Watch item"),
                font=("Arial", 13, "bold"),
                text_color=TEXT,
            ).pack(side="left")

            ctk.CTkLabel(
                heading,
                text=str(item.get("count", 0)),
                font=("Arial", 16, "bold"),
                text_color=PRIMARY,
            ).pack(side="right")

            ctk.CTkLabel(
                card,
                text=item.get("description", ""),
                font=("Arial", 11),
                text_color=MUTED_TEXT,
                justify="left",
                anchor="w",
                wraplength=480,
            ).pack(fill="x", padx=14, pady=(0, 12))


    def _build_editor_actions(self, parent):
        panel = self._panel(
            parent,
            "Editorial Actions",
            "Stage 3 prepares the workflow that will become active in Version 2.3.",
        )

        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=15, pady=(0, 18))
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="actions")

        actions = (
            (
                "Generate Story",
                "Create website, Facebook and newsletter copy from a selected application.",
            ),
            (
                "Create Follow-up",
                "Turn editorial recommendations into a reporting checklist.",
            ),
            (
                "Send to Story Desk",
                "Move the selected application into the future newsroom workflow.",
            ),
        )

        for column, (title, description) in enumerate(actions):
            card = ctk.CTkFrame(
                grid,
                fg_color=CARD_BG,
                corner_radius=10,
                border_width=1,
                border_color=BORDER,
            )
            card.grid(row=0, column=column, sticky="nsew", padx=5)

            ctk.CTkLabel(
                card,
                text=title,
                font=("Arial", 14, "bold"),
                text_color=TEXT,
            ).pack(pady=(14, 5))

            ctk.CTkLabel(
                card,
                text=description,
                font=("Arial", 11),
                text_color=MUTED_TEXT,
                justify="center",
                wraplength=300,
            ).pack(padx=12, pady=(0, 12))

            ctk.CTkButton(
                card,
                text="Coming in Version 2.3",
                state="disabled",
                height=34,
            ).pack(padx=14, pady=(0, 14), fill="x")

    def _build_top_stories(self, parent):
        panel = self._panel(
            parent,
            "Top Planning Stories",
            "The five strongest applications, ranked with editorial priority and story tags.",
        )

        stories = self.report_data.get("top_stories", [])

        if not stories:
            ctk.CTkLabel(
                panel,
                text="No applications were available for this report.",
                font=("Arial", 13),
                text_color=MUTED_TEXT,
            ).pack(anchor="w", padx=20, pady=(0, 18))
            return

        for position, story in enumerate(stories, start=1):
            self._build_story_card(panel, position, story)

        ctk.CTkLabel(panel, text="", height=8).pack()

    def _build_story_card(self, parent, position, story):
        card = ctk.CTkFrame(
            parent,
            fg_color=CARD_BG,
            corner_radius=11,
            border_width=1,
            border_color=BORDER,
        )
        card.pack(fill="x", padx=20, pady=(0, 10))

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=15, pady=(13, 7))

        priority = story.get("editorial_priority", "WEBSITE STORY")
        ctk.CTkLabel(
            top,
            text=f"{position}",
            width=32,
            height=32,
            font=("Arial", 14, "bold"),
            text_color="#ffffff",
            fg_color=PRIMARY,
            corner_radius=16,
        ).pack(side="left")

        ctk.CTkLabel(
            top,
            text=priority,
            font=("Arial", 12, "bold"),
            text_color="#ffffff",
            fg_color=self._priority_colour(priority),
            corner_radius=7,
            padx=10,
            pady=5,
        ).pack(side="left", padx=(10, 0))

        score = int(story.get("score", 0))
        stars = "★" * int(story.get("priority_stars", 1))
        ctk.CTkLabel(
            top,
            text=f"{stars}  {score}",
            font=("Arial", 14, "bold"),
            text_color=GOLD,
        ).pack(side="right")

        proposal = (
            story.get("proposal_summary")
            or story.get("proposal")
            or "Proposal details unavailable"
        )
        ctk.CTkLabel(
            card,
            text=proposal,
            font=("Arial", 15, "bold"),
            text_color=TEXT,
            justify="left",
            anchor="w",
            wraplength=1020,
        ).pack(fill="x", padx=15, pady=(0, 7))

        metadata = (
            f"📍 {story.get('area') or 'Unknown area'}    •    "
            f"{story.get('reference') or 'No reference'}    •    "
            f"{story.get('decision') or story.get('status') or 'No decision recorded'}"
        )
        ctk.CTkLabel(
            card,
            text=metadata,
            font=("Arial", 11),
            text_color=MUTED_TEXT,
            justify="left",
            anchor="w",
            wraplength=1020,
        ).pack(fill="x", padx=15, pady=(0, 8))

        self._social_workflow_badge(card, story)

        self._build_tags(card, story.get("tags", []), padx=15)

        reason = next(
            iter(story.get("why_news", [])),
            "Worth monitoring for local impact or public interest",
        )
        ctk.CTkLabel(
            card,
            text=f"Why it matters: {reason}",
            font=("Arial", 11),
            text_color=TEXT,
            justify="left",
            anchor="w",
            wraplength=1020,
        ).pack(fill="x", padx=15, pady=(10, 6))

        follow_up = story.get("follow_up", [])
        if follow_up:
            ctk.CTkLabel(
                card,
                text=f"Suggested follow-up: {follow_up[0]}",
                font=("Arial", 11),
                text_color=PRIMARY,
                justify="left",
                anchor="w",
                wraplength=1020,
            ).pack(fill="x", padx=15, pady=(0, 9))

        button_row = ctk.CTkFrame(card, fg_color="transparent")
        button_row.pack(fill="x", padx=15, pady=(0, 13))

        ctk.CTkButton(
                button_row,
                text="Generate Story",
                width=150,
                height=32,
                fg_color=ACTION_BLUE,
                hover_color=ACTION_BLUE_HOVER,
                command=lambda s=story: open_story_desk(self.window, s),
        ).pack(side="left")

        ctk.CTkButton(
                button_row,
                text="Add to Socials",
                width=150,
                height=32,
                fg_color=BRAND_RED,
                hover_color=BRAND_RED_HOVER,
                command=lambda s=story: self._add_planning_to_socials(s),
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            button_row,
            text="Open Source",
            width=130,
            height=32,
            fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,
            command=lambda s=story: self._open_planning_source(s),
        ).pack(side="left", padx=(8, 0))

    def _add_planning_to_socials(self, application):
        add_story_to_social_desk(
            self.window,
            planning_story(application),
            module_key="planning",
        )

    def _open_planning_source(self, application):
        story = planning_story(application)
        if story.url:
            webbrowser.open(story.url)

    def _build_full_register(self, parent):
        section = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        section.pack(fill="x", pady=(0, 18))

        ctk.CTkLabel(
            section,
            text="📋 FULL PLANNING REGISTER",
            font=("Arial", 20, "bold"),
            text_color=TEXT,
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            section,
            text=(
                "Every application from the latest download, "
                "without editorial scores or rankings."
            ),
            font=("Arial", 14),
            text_color=MUTED_TEXT,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        search_row = ctk.CTkFrame(section, fg_color="transparent")
        search_row.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            search_row,
            text="Search:",
            font=("Arial", 14, "bold"),
            text_color=TEXT,
        ).pack(side="left", padx=(0, 8))

        search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self.search_var,
            placeholder_text=(
                "Search proposal, area, address, reference or category..."
            ),
            height=38,
            fg_color=ENTRY_BG,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text_color=MUTED_TEXT,
        )
        search_entry.pack(side="left", fill="x", expand=True)

        search_entry.bind(
            "<KeyRelease>",
            lambda _event: self._filter_register(),
        )

        ctk.CTkButton(
            search_row,
            text="Clear",
            width=90,
            height=38,
            fg_color="#374151",
            hover_color="#475569",
            command=self._clear_search,
        ).pack(side="left", padx=(8, 0))

        controls = ctk.CTkFrame(section, fg_color="transparent")
        controls.pack(fill="x", padx=20, pady=(0, 10))

        self.register_count_label = ctk.CTkLabel(
            controls,
            text="",
            font=("Arial", 13, "bold"),
            text_color=TEXT,
        )
        self.register_count_label.pack(side="left")

        button_row = ctk.CTkFrame(controls, fg_color="transparent")
        button_row.pack(side="right")

        ctk.CTkButton(
            button_row,
            text="Copy Plain Text",
            width=145,
            fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,
            command=self._copy_plain_text,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            button_row,
            text="Copy Website",
            width=135,
            fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,
            command=self._copy_website,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            button_row,
            text="Copy Facebook",
            width=135,
            fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,
            command=self._copy_facebook,
        ).pack(side="left", padx=4)

        self.copy_status_label = ctk.CTkLabel(
            section,
            text="",
            font=("Arial", 12),
            text_color="#22c55e",
        )
        self.copy_status_label.pack(
            anchor="e",
            padx=20,
            pady=(0, 6),
        )

        selection_actions = ctk.CTkFrame(section, fg_color="transparent")
        selection_actions.pack(fill="x", padx=20, pady=(0, 10))
        action_definitions = (
            ("GENERATE STORY", ACTION_BLUE, ACTION_BLUE_HOVER,
             self._generate_selected_register_story),
            ("ADD TO SOCIALS", BRAND_RED, BRAND_RED_HOVER,
             self._social_selected_register_story),
            ("OPEN SOURCE", ACTION_BLUE, ACTION_BLUE_HOVER,
             self._open_selected_register_source),
        )
        self.register_action_buttons = []
        for label, colour, hover, command in action_definitions:
            button = ctk.CTkButton(
                selection_actions, text=label, width=165, height=36,
                fg_color=colour, hover_color=hover, state="disabled",
                command=command,
            )
            button.pack(side="left", padx=(0, 8))
            self.register_action_buttons.append(button)

        table_frame = ctk.CTkFrame(
            section, fg_color=ENTRY_BG, border_width=1, border_color=BORDER
        )
        table_frame.pack(fill="x", padx=20, pady=(0, 20))
        style = ttk.Style(self.window)
        style.theme_use("clam")
        style.configure(
            "Planning.Treeview", background=ENTRY_BG,
            fieldbackground=ENTRY_BG, foreground=TEXT, rowheight=38,
            borderwidth=0, font=("Arial", 14),
        )
        style.configure(
            "Planning.Treeview.Heading", background="#334155",
            foreground=TEXT, font=("Arial", 13, "bold"),
        )
        style.map("Planning.Treeview", background=[("selected", ACTION_BLUE)])
        self.register_tree = ttk.Treeview(
            table_frame, columns=("reference", "authority", "area", "proposal"),
            show="headings", style="Planning.Treeview",
            selectmode="browse", height=14,
        )
        for key, label, width in (
            ("reference", "REFERENCE", 150),
            ("authority", "AUTHORITY", 230),
            ("area", "AREA", 170),
            ("proposal", "PROPOSAL", 650),
        ):
            self.register_tree.heading(key, text=label)
            self.register_tree.column(
                key, width=width, anchor="w", stretch=(key == "proposal")
            )
        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.register_tree.yview
        )
        self.register_tree.configure(yscrollcommand=scrollbar.set)
        self.register_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.register_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._select_register_story()
        )

        self._refresh_register()

    def _clear_search(self):
        self.search_var.set("")
        self._filter_register()

    def _filter_register(self):
        query = self.search_var.get().strip().lower()

        if not query:
            self.filtered_applications = list(self.all_applications)
        else:
            self.filtered_applications = [
                application
                for application in self.all_applications
                if query in self._application_search_text(application)
            ]

        self._refresh_register()

    def _application_search_text(self, application):
        values = (
            application.get("proposal"),
            application.get("proposal_summary"),
            application.get("address"),
            application.get("area"),
            application.get("reference"),
            application.get("planning_authority"),
            application.get("category"),
            application.get("status"),
            application.get("decision"),
        )

        return " ".join(
            str(value or "").lower()
            for value in values
        )

    def _refresh_register(self):
        if self.register_tree is None:
            return

        applications = self.filtered_applications
        total = len(self.all_applications)
        visible = len(applications)

        if self.register_count_label is not None:
            if visible == total:
                count_text = f"{total} applications"
            else:
                count_text = f"{visible} of {total} applications"

            self.register_count_label.configure(text=count_text)

        self.register_selected_application = None
        for button in self.register_action_buttons:
            button.configure(state="disabled")
        self.register_tree.delete(*self.register_tree.get_children())
        self._register_rows = self._sorted_applications(applications)
        for index, application in enumerate(self._register_rows):
            values = self._application_values(application)
            self.register_tree.insert(
                "", "end", iid=str(index),
                values=(
                    values["reference"],
                    values["planning_authority"],
                    values["area"],
                    values["proposal"],
                ),
            )

    def _select_register_story(self):
        selected = self.register_tree.selection() if self.register_tree else ()
        if not selected:
            self.register_selected_application = None
            for button in self.register_action_buttons:
                button.configure(state="disabled")
            return
        self.register_selected_application = self._register_rows[int(selected[0])]
        for button in self.register_action_buttons:
            button.configure(state="normal")

    def _generate_selected_register_story(self):
        if self.register_selected_application is not None:
            open_story_desk(self.window, self.register_selected_application)

    def _social_selected_register_story(self):
        if self.register_selected_application is not None:
            self._add_planning_to_socials(self.register_selected_application)

    def _open_selected_register_source(self):
        if self.register_selected_application is not None:
            self._open_planning_source(self.register_selected_application)

    def _sorted_applications(self, applications):
        return sorted(
            applications,
            key=lambda application: (
                str(application.get("area") or "").lower(),
                str(application.get("address") or "").lower(),
                str(application.get("reference") or "").lower(),
            ),
        )

    def _application_values(self, application):
        proposal = (
            application.get("proposal_summary")
            or application.get("proposal")
            or "Proposal details unavailable"
        )

        address = (
            application.get("address")
            or application.get("site_address")
            or "Address unavailable"
        )

        area = (
            application.get("area")
            or "Unknown area"
        )

        reference = (
            application.get("reference")
            or "No reference"
        )

        planning_authority = (
            application.get("planning_authority")
            or "Planning authority unavailable"
        )

        category = (
            application.get("category")
            or "Uncategorised"
        )

        decision = (
            application.get("decision")
            or application.get("status")
            or "No decision recorded"
        )

        return {
            "proposal": proposal,
            "address": address,
            "area": area,
            "reference": reference,
            "planning_authority": planning_authority,
            "category": category,
            "decision": decision,
        }

    def _format_plain_text(self, applications):
        if not applications:
            return "No planning applications match the current search."

        lines = [
            "LINCOLNSHIRE PLANNING REGISTER",
            "",
        ]

        sorted_applications = self._sorted_applications(applications)

        for position, application in enumerate(
            sorted_applications,
            start=1,
        ):
            values = self._application_values(application)

            lines.extend(
                [
                    f"{position}. {values['proposal']}",
                    "",
                    f"Location: {values['address']}",
                    f"Area: {values['area']}",
                    f"Reference: {values['reference']}",
                    f"Planning authority: {values['planning_authority']}",
                    f"Category: {values['category']}",
                    f"Decision/Status: {values['decision']}",
                    "",
                    "────────────────────────────────────────",
                    "",
                ]
            )

        return "\n".join(lines).rstrip()

    def _format_website(self, applications):
        if not applications:
            return "No planning applications match the current search."

        sorted_applications = self._sorted_applications(applications)

        lines = [
            "# Planning applications across Lincolnshire",
            "",
            (
                "Here is the latest full list of planning applications "
                "downloaded by Devour Lincolnshire NewsDesk."
            ),
            "",
        ]

        current_area = None

        for application in sorted_applications:
            values = self._application_values(application)
            area = values["area"]

            if area != current_area:
                lines.extend(
                    [
                        f"## {area}",
                        "",
                    ]
                )
                current_area = area

            lines.extend(
                [
                    f"### {values['proposal']}",
                    "",
                    f"**Location:** {values['address']}",
                    "",
                    f"**Reference:** {values['reference']}",
                    "",
                    f"**Planning authority:** {values['planning_authority']}",
                    "",
                    f"**Category:** {values['category']}",
                    "",
                    f"**Decision/Status:** {values['decision']}",
                    "",
                    "---",
                    "",
                ]
            )

        return "\n".join(lines).rstrip()

    def _format_facebook(self, applications):
        if not applications:
            return "No planning applications match the current search."

        sorted_applications = self._sorted_applications(applications)

        lines = [
            "🏛 PLANNING APPLICATIONS ACROSS LINCOLNSHIRE",
            "",
            (
                f"Here is the latest list of "
                f"{len(sorted_applications)} planning applications "
                "downloaded by Devour Lincolnshire NewsDesk."
            ),
            "",
        ]

        for position, application in enumerate(
            sorted_applications,
            start=1,
        ):
            values = self._application_values(application)

            lines.extend(
                [
                    f"{position}. {values['proposal']}",
                    f"📍 {values['address']}",
                    f"📄 {values['reference']}",
                    f"🏛 {values['planning_authority']}",
                    f"🏷️ {values['category']}",
                    f"📌 {values['decision']}",
                    "",
                    "────────────────────",
                    "",
                ]
            )

        return "\n".join(lines).rstrip()

    def _copy_to_clipboard(self, text, message):
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()

        if self.copy_status_label is not None:
            self.copy_status_label.configure(text=message)
            self.window.after(
                2500,
                lambda: self.copy_status_label.configure(text=""),
            )

    def _copy_plain_text(self):
        text = self._format_plain_text(
            self.filtered_applications
        )
        self._copy_to_clipboard(
            text,
            "Plain-text register copied.",
        )

    def _copy_website(self):
        text = self._format_website(
            self.filtered_applications
        )
        self._copy_to_clipboard(
            text,
            "Website register copied.",
        )

    def _copy_facebook(self):
        text = self._format_facebook(
            self.filtered_applications
        )
        self._copy_to_clipboard(
            text,
            "Facebook register copied.",
        )

    def _build_tags(self, parent, tags, padx=0):
        tag_row = ctk.CTkFrame(parent, fg_color="transparent")
        tag_row.pack(fill="x", padx=padx)

        for tag in tags:
            ctk.CTkLabel(
                tag_row,
                text=tag,
                font=("Arial", 10, "bold"),
                text_color="#ffffff",
                fg_color=self._tag_colour(tag),
                corner_radius=7,
                padx=9,
                pady=4,
            ).pack(side="left", padx=(0, 6))


def open_planning_report(parent, report_data, refresh_command=None):
    return PlanningReportWindow(
        parent,
        report_data,
        refresh_command=refresh_command,
    )
