"""Council Intelligence workspace for NewsDesk Pro."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from queue import Empty, Queue
import threading
import webbrowser
import zipfile
from tkinter import filedialog, messagebox

import customtkinter as ctk

from newsdesk.action_bar import NewsDeskActionBar
from newsdesk.display_dates import format_uk_date
from newsdesk.image_preview_cache import IMAGE_PREVIEW_CACHE
from newsdesk.services.council_service import CouncilCollectionService
from newsdesk.feed_policy import prepare_lincolnshire_feed, published_datetime
from newsdesk.sources.council_scraper import load_council_config
from newsdesk.story_queue import NewsDeskStoryQueue
from newsdesk.header import NewsDeskHeader
from newsdesk.social.selection import add_story_to_social_desk
from modules.sport_source_manager import SourceManagerWindow
from newsdesk.story_engine import StoryEngine
from newsdesk.story import Story
from newsdesk.theme import (
    ACCENT, ACCENT_HOVER, APP_BG, BORDER, BRAND_RED, BRAND_RED_HOVER,
    CARD_BG, HEADER_BG, LOGO_PATH, PANEL_BG, SUCCESS, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, PANEL_CORNER_RADIUS,
    STANDARD_BORDER_WIDTH, HEADER_HEIGHT, LOGO_SIZE,
)
from newsdesk.ui_support import (
    DEFAULT_SEARCH_DEBOUNCE_MS,
    DebouncedAction,
    IntelligenceWindowSupport,
    focus_existing_window,
    maximize_window,
)
from modules.fire import FireIntelligenceWindow as _EstablishedEditorialWorkspace


ALL_SOURCES = "All Sources"
ALL_CATEGORIES = "All Categories"
SOURCE_NAMES = tuple(
    source.name for source in load_council_config()["sources"] if source.enabled
)


class CouncilIntelligenceWindow(ctk.CTkToplevel):
    """Collect, filter and review recent official Council news."""

    def __init__(self, master=None, *, collection_service_factory=None):
        super().__init__(master)
        self._window_support = IntelligenceWindowSupport(self, master)
        self._window_support.install()
        self.collection_service_factory = (
            collection_service_factory or CouncilCollectionService
        )
        self.stories = []
        self.publish_results = {}
        self.errors = []
        self.source_health = {}
        self.selected_story = None
        self.selected_result = None
        self.source_manager_window = None
        self._story_engine = StoryEngine(
            strict_validation=False,
            strict_formatting=False,
        )
        self.is_refreshing = False
        self._refresh_events: Queue = Queue()

        self.title("Council Intelligence - Devour Lincolnshire NewsDesk")
        self.geometry("1450x900")
        self.minsize(1150, 720)
        self.configure(fg_color=APP_BG)
        if master is not None:
            self.transient(master)

        self.search_var = ctk.StringVar(value="")
        self._search_debounce = DebouncedAction(
            self._window_support,
            DEFAULT_SEARCH_DEBOUNCE_MS,
            self._refresh_visible_queue,
        )
        self._build_layout()
        self._window_support.call_later(100, lambda: maximize_window(self))

    def _build_layout(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._build_statistics()
        self._build_workspace()
        self._build_status_bar()

    def _build_header(self):
        self.header = NewsDeskHeader(
            self,
            module_title="Council Intelligence",
            subtitle="Collect  •  Lincolnshire  •  Review official local government news",
            primary_button_text="REFRESH COUNCIL NEWS",
            primary_command=self._refresh_council_news,
            close_command=self._window_support.close,
            secondary_actions=(
                ("MANAGE SOURCES", self._open_source_manager),
                ("SOCIAL DESK", self._open_social_desk),
            ),
            height=HEADER_HEIGHT,
        )
        self.header.grid(row=0, column=0, sticky="ew")
        self.refresh_button = self.header.primary_button

    def _open_source_manager(self):
        if focus_existing_window(self.source_manager_window):
            return
        self.source_manager_window = SourceManagerWindow(
            self,
            module_profile="council",
            on_refresh=self._refresh_council_news,
        )

    def _open_social_desk(self):
        from modules.social_desk import open_social_desk
        return open_social_desk(self)

    def _build_statistics(self):
        panel = ctk.CTkFrame(self, fg_color=APP_BG)
        panel.grid(row=1, column=0, sticky="ew", padx=22, pady=(14, 8))
        for column in range(5):
            panel.grid_columnconfigure(column, weight=1, uniform="council-stats")
        definitions = (
            ("total", "TOTAL STORIES", TEXT_PRIMARY),
            ("today", "TODAY", SUCCESS),
            ("recent", "PREVIOUS 3 DAYS", TEXT_PRIMARY),
            ("older", "OLDER", TEXT_MUTED),
            ("selected", "SELECTED STORY", ACCENT),
        )
        self.stat_labels = {}
        for column, (key, label, colour) in enumerate(definitions):
            card = ctk.CTkFrame(
                panel, fg_color=CARD_BG, corner_radius=PANEL_CORNER_RADIUS,
                border_width=STANDARD_BORDER_WIDTH, border_color=BORDER,
            )
            card.grid(row=0, column=column, sticky="ew", padx=5)
            ctk.CTkLabel(card, text=label, font=("Arial", 10, "bold"), text_color=TEXT_MUTED).pack(pady=(11, 2))
            value = ctk.CTkLabel(card, text="0", font=("Arial", 25, "bold"), text_color=colour)
            value.pack(pady=(0, 10))
            self.stat_labels[key] = value

    def _build_workspace(self):
        workspace = ctk.CTkFrame(self, fg_color=APP_BG)
        workspace.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 12))
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=0, minsize=430)
        workspace.grid_columnconfigure(1, weight=1)
        self._build_story_queue(workspace)
        self._build_detail_panel(workspace)

    def _build_story_queue(self, parent):
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        filters = ctk.CTkFrame(left, fg_color=HEADER_BG, corner_radius=12)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        filters.grid_columnconfigure((0, 1), weight=1)
        self.search_entry = ctk.CTkEntry(
            filters, textvariable=self.search_var,
            placeholder_text="Search headline, place or subject...",
            height=32, fg_color=CARD_BG, border_color=BORDER,
        )
        self.search_entry.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(9, 5))
        self.search_var.trace_add("write", lambda *_: self._search_debounce.schedule())
        self.source_menu = self._option(filters, (ALL_SOURCES, *SOURCE_NAMES), 1, 0)
        self.category_menu = self._option(filters, (ALL_CATEGORIES,), 2, 0)
        ctk.CTkButton(
            filters, text="RESET FILTERS", height=30, fg_color="#374151",
            hover_color="#475569", command=self._reset_filters,
        ).grid(row=1, column=1, rowspan=2, sticky="ew", padx=(4, 10), pady=(4, 9))
        self.story_queue = NewsDeskStoryQueue(
            left,
            title="COUNCIL STORY QUEUE",
            empty_title="No Council stories loaded.",
            empty_message="Refresh Council Intelligence to collect official releases.",
            on_story_selected=self._handle_queue_selection,
        )
        self.story_queue.grid(row=1, column=0, sticky="nsew")
        self.story_queue.filter_menu.grid_remove()

    def _option(self, parent, values, row, column):
        menu = ctk.CTkOptionMenu(
            parent, values=list(values), height=30, fg_color=CARD_BG,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            command=lambda _value: self._refresh_visible_queue(),
        )
        menu.grid(row=row, column=column, sticky="ew", padx=(10 if column == 0 else 4, 4 if column == 0 else 10), pady=4)
        menu.set(values[0])
        return menu

    def _build_detail_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=HEADER_BG, corner_radius=16, border_width=1, border_color=BORDER)
        panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            panel, text="STORY REVIEW", font=("Arial", 16, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 10))
        self.detail_content = ctk.CTkScrollableFrame(panel, fg_color=PANEL_BG, corner_radius=12)
        self.detail_content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.review_content = self.detail_content
        self.action_bar = NewsDeskActionBar(panel, command=self._run_action)
        self.action_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.action_buttons = self.action_bar.buttons
        self._show_detail_placeholder()

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0)
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(bar, text="Ready", text_color=TEXT_MUTED, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=18, pady=7)

    def _refresh_council_news(self):
        if self.is_refreshing:
            return
        self.is_refreshing = True
        self.refresh_button.configure(state="disabled", text="REFRESHING...")
        self.status_label.configure(text="Refreshing Council sources...")
        threading.Thread(target=self._collect_worker, daemon=True, name="council-refresh").start()
        self._window_support.call_later(100, self._poll_collection)

    def _collect_worker(self):
        try:
            self._refresh_events.put(("complete", self.collection_service_factory().collect()))
        except Exception as error:
            self._refresh_events.put(("failed", str(error)))

    def _poll_collection(self):
        try:
            event, payload = self._refresh_events.get_nowait()
        except Empty:
            self._window_support.call_later(100, self._poll_collection)
            return
        if event == "failed":
            self.is_refreshing = False
            self.refresh_button.configure(state="normal", text="REFRESH COUNCIL NEWS")
            self.status_label.configure(text=f"Failed: {payload}")
            return
        try:
            self._collection_complete(
                payload.stories,
                payload.errors,
                payload.source_health_payload(),
                notify_dashboard=True,
            )
        except Exception as error:
            self.is_refreshing = False
            self.refresh_button.configure(
                state="normal", text="REFRESH COUNCIL NEWS"
            )
            self.status_label.configure(text=f"Failed: {error}")

    def _collection_complete(self, stories, errors, source_health, *, notify_dashboard):
        self.stories = prepare_lincolnshire_feed(stories)
        self.errors = list(errors)
        self.source_health = dict(source_health or {})
        self.selected_story = None
        self.selected_result = None
        self.is_refreshing = False
        self.refresh_button.configure(state="normal", text="REFRESH COUNCIL NEWS")
        self._refresh_categories()
        self._update_statistics()
        self._refresh_visible_queue()
        self._show_detail_placeholder()
        failed_sources = sum(not value.get("successful", False) for value in self.source_health.values())
        self.status_label.configure(
            text=(
                f"Completed with source errors — {len(self.stories)} stories"
                if failed_sources or errors
                else f"Completed — {len(self.stories)} Council stories"
            )
        )
        if notify_dashboard:
            self._window_support.notify_dashboard({
                "stories": self.stories,
                "publish_results": {},
                "errors": self.errors,
                "source_health": self.source_health,
            })

    def load_stories(self, stories, publish_results=None, errors=None, source_health=None):
        """Load a completed Home payload without recollecting."""
        self.publish_results = dict(publish_results or {})
        self._collection_complete(
            stories, errors or [], source_health or {}, notify_dashboard=False
        )
        self.status_label.configure(text=f"Loaded {len(self.stories)} Council stories from NewsDesk Pro Home")

    def _refresh_categories(self):
        current = self.category_menu.get()
        values = [ALL_CATEGORIES, *sorted({story.category for story in self.stories if story.category}, key=str.casefold)]
        self.category_menu.configure(values=values)
        self.category_menu.set(current if current in values else ALL_CATEGORIES)

    def _reset_filters(self):
        self.search_var.set("")
        self.source_menu.set(ALL_SOURCES)
        self.category_menu.set(ALL_CATEGORIES)
        self._refresh_visible_queue()

    def _refresh_visible_queue(self):
        self._search_debounce.cancel()
        query = self.search_var.get().strip().casefold()
        source = self.source_menu.get()
        category = self.category_menu.get()
        visible = [
            story for story in self.stories
            if (source == ALL_SOURCES or story.source == source)
            and (category == ALL_CATEGORIES or story.category == category)
            and (not query or query in self._searchable_text(story))
        ]
        visible.sort(key=lambda story: (self._published_timestamp(story), story.title.casefold()), reverse=True)
        if self.selected_story is not None and self.selected_story not in visible:
            self.selected_story = None
            self._show_detail_placeholder()
        self.story_queue.set_empty_state(
            title="No stories match the current search and filters.",
            message="Reset or change the Council filters to see more stories.",
        )
        self.story_queue.set_stories(self._queue_mapping(story) for story in visible)
        self.status_label.configure(text=f"Showing {len(visible)} of {len(self.stories)} Council stories")

    @staticmethod
    def _searchable_text(story):
        return " ".join((story.title, story.summary, story.body, story.source, story.category, story.location)).casefold()

    @staticmethod
    def _published_timestamp(story):
        try:
            value = datetime.fromisoformat(story.published.replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _queue_mapping(story):
        reason = CouncilIntelligenceWindow._queue_reason(story)
        completeness = "SUMMARY ONLY" if story.extras.get("content_completeness") == "summary_only" else ""
        summary = " | ".join(value for value in (completeness, story.category, reason) if value)
        return {
            "id": id(story), "title": story.title, "summary": summary,
            "priority": "", "source": story.source,
            "published": CouncilIntelligenceWindow._format_date(story.published),
            "story": story,
        }

    @staticmethod
    def _format_date(value):
        return format_uk_date(value)

    @staticmethod
    def _queue_reason(story):
        locations = list(story.extras.get("matched_locations") or [])
        if locations:
            return f"Direct {locations[0]} match"
        return "Official Lincolnshire council source"

    def _handle_queue_selection(self, mapping):
        story = mapping.get("story")
        if story in self.stories:
            self.selected_story = story
            self.selected_result = self.publish_results.get(id(story))
            if self.selected_result is None:
                try:
                    output_story = Story.from_dict(story.to_dict())
                    output_story.published = self._format_date(story.published)
                    self.selected_result = self._story_engine.process(output_story)
                    self.publish_results[id(story)] = self.selected_result
                except Exception:
                    self.selected_result = None
            self._show_story(story)
            self.stat_labels["selected"].configure(text="1")

    def _clear_detail(self):
        for child in self.detail_content.winfo_children():
            child.destroy()

    def _show_detail_placeholder(self):
        self._clear_detail()
        ctk.CTkLabel(
            self.detail_content, text="SELECT A COUNCIL STORY",
            font=("Arial", 20, "bold"), text_color=TEXT_PRIMARY,
        ).pack(pady=(90, 10))
        ctk.CTkLabel(
            self.detail_content,
            text="Choose a story to inspect its location evidence and article text.",
            text_color=TEXT_MUTED, wraplength=600,
        ).pack()
        if hasattr(self, "action_bar"):
            self.action_bar.disable_all()

    def _show_story(self, story):
        self._clear_detail()
        ctk.CTkLabel(
            self.detail_content, text=story.title, font=("Arial", 23, "bold"),
            text_color=TEXT_PRIMARY, justify="left", anchor="w", wraplength=760,
        ).pack(fill="x", padx=22, pady=(20, 10))
        from newsdesk.social.selection import social_workflow_status
        workflow_status = social_workflow_status(story)
        if workflow_status:
            ctk.CTkLabel(
                self.detail_content, text=workflow_status,
                font=("Arial", 11, "bold"),
                text_color="#22c55e" if workflow_status == "SENT TO METRICOOL" else "#60a5fa",
                anchor="w",
            ).pack(fill="x", padx=22, pady=(0, 7))
        locations = ", ".join(story.extras.get("matched_locations") or [])
        metadata = "  |  ".join(
            value for value in (
                story.source, self._format_date(story.published),
                story.category, locations,
                "SUMMARY ONLY" if story.extras.get("content_completeness") == "summary_only" else "",
            ) if value
        )
        ctk.CTkLabel(
            self.detail_content, text=metadata, text_color=TEXT_SECONDARY,
            anchor="w", justify="left", wraplength=760,
        ).pack(fill="x", padx=22, pady=(0, 8))
        self._workspace_image(story)
        if story.summary:
            self._detail_section("SUMMARY", story.summary)
        if story.body:
            self._detail_section("ARTICLE", story.body)
        self.action_bar.enable_all()
        self._reset_workspace_scroll()
        self.status_label.configure(text=f"Status: Selected — {story.title}")

    def _detail_section(self, heading, text):
        frame = ctk.CTkFrame(self.detail_content, fg_color=CARD_BG, corner_radius=10)
        frame.pack(fill="x", padx=22, pady=(0, 12))
        ctk.CTkLabel(frame, text=heading, font=("Arial", 11, "bold"), text_color=TEXT_MUTED, anchor="w").pack(fill="x", padx=14, pady=(12, 5))
        ctk.CTkLabel(frame, text=text, text_color=TEXT_PRIMARY, justify="left", anchor="w", wraplength=730).pack(fill="x", padx=14, pady=(0, 13))

    def _workspace_image(self, story):
        local_path = str(story.image_local_path or "").strip()
        usable = bool(local_path) and Path(local_path).is_file() and not story.image_is_fallback
        if not usable:
            frame = ctk.CTkFrame(self.detail_content, fg_color=CARD_BG, corner_radius=10)
            frame.pack(fill="x", padx=22, pady=(0, 12))
            ctk.CTkLabel(
                frame, text="No usable source image was available.",
                text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=14, pady=14)
            self._image_action_row(frame, image_available=False)
            return
        preview = IMAGE_PREVIEW_CACHE.get(local_path, (760, 380))
        if preview is None:
            return
        frame = ctk.CTkFrame(self.detail_content, fg_color=CARD_BG, corner_radius=10)
        frame.pack(fill="x", padx=22, pady=(0, 12))
        image = ctk.CTkImage(preview, preview, size=preview.size)
        label = ctk.CTkLabel(frame, text="", image=image)
        label.image = image
        label.pack(padx=10, pady=10)
        image_path = Path(local_path)
        ctk.CTkLabel(
            frame, text=f"Image credit: {self._selected_image_credit(story)}",
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            frame, text=self._image_quality_details(story, image_path)["display"],
            text_color=TEXT_MUTED, anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 8))
        self._image_action_row(frame, image_available=True)

    def _image_action_row(self, parent, *, image_available):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 10))
        actions = (
            ("COPY IMAGE", self._copy_selected_image, image_available),
            ("COPY CREDIT", self._copy_selected_image_credit, image_available),
            ("SAVE IMAGE AS...", self._save_selected_image, image_available),
            ("OPEN IMAGE", self._open_selected_image, image_available),
            ("SHOW IN FOLDER", self._show_selected_image_folder, image_available),
            ("STORY PACK", self._export_selected_story_pack, True),
        )
        for column, (label, command, enabled) in enumerate(actions):
            row.grid_columnconfigure(column, weight=1)
            ctk.CTkButton(
                row, text=label, command=command, height=32,
                fg_color=BORDER, hover_color="#475569",
                state="normal" if enabled else "disabled",
                font=("Arial", 9, "bold"),
            ).grid(row=0, column=column, sticky="ew", padx=3)

    def _reset_workspace_scroll(self):
        canvas = getattr(self.detail_content, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0)

    # Reuse the established Fire/Police image-management implementations.
    _selected_image_path = _EstablishedEditorialWorkspace._selected_image_path
    _selected_image_credit = _EstablishedEditorialWorkspace._selected_image_credit
    _copy_selected_image = _EstablishedEditorialWorkspace._copy_selected_image
    _copy_selected_image_credit = _EstablishedEditorialWorkspace._copy_selected_image_credit
    _save_selected_image = _EstablishedEditorialWorkspace._save_selected_image
    _open_selected_image = _EstablishedEditorialWorkspace._open_selected_image
    _show_selected_image_folder = _EstablishedEditorialWorkspace._show_selected_image_folder
    _safe_filename = staticmethod(_EstablishedEditorialWorkspace._safe_filename)
    _image_quality_details = _EstablishedEditorialWorkspace._image_quality_details
    _with_image_credit = _EstablishedEditorialWorkspace._with_image_credit

    def _selected_publication_outputs(self):
        outputs = {"website": "", "facebook": "", "newsletter": ""}
        if self.selected_result is None:
            return outputs
        for channel in outputs:
            value = str(getattr(self.selected_result, channel, "") or "").strip()
            if value:
                outputs[channel] = self._with_image_credit(value, channel=channel)
        return outputs

    def _run_action(self, action_name):
        if self.selected_story is None:
            return
        if action_name == "ADD TO NEWSLETTER":
            open_newsletter_action(
                self, self.selected_story, module_key="council",
                newsletter_copy=str(
                    getattr(self.selected_result, "website", "") or ""
                ).strip(),
                on_changed=lambda: configure_newsletter_action(
                    self.action_bar, self.selected_story,
                ),
            )
            return
        if action_name == "ADD TO SOCIALS":
            draft = add_story_to_social_desk(
                self, self.selected_story, module_key="council",
            )
            if draft is not None:
                self._show_story(self.selected_story)
            return
        if action_name == "OPEN SOURCE":
            if self.selected_story.url:
                webbrowser.open(self.selected_story.url)
                self.status_label.configure(text="Status: Source opened in browser.")
            return
        field = {
            "WEBSITE ARTICLE": "website",
            "FACEBOOK POST": "facebook",
            "NEWSLETTER COPY": "newsletter",
        }.get(action_name)
        if not field:
            return
        output = self._selected_publication_outputs().get(field, "")
        if not output:
            messagebox.showwarning(
                "Publishing output unavailable",
                f"No {action_name.lower()} was generated for this story.",
                parent=self,
            )
            return
        self._show_output_window(action_name, output)

    def _show_output_window(self, title, content):
        window = ctk.CTkToplevel(self)
        window.title(f"{title.title()} - Council Intelligence")
        window.geometry("900x700")
        window.minsize(650, 480)
        window.configure(fg_color=APP_BG)
        window.transient(self)
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            window, text=title, font=("Arial", 19, "bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 12))
        textbox = ctk.CTkTextbox(
            window, fg_color=PANEL_BG, border_width=1,
            border_color=BORDER, text_color=TEXT_PRIMARY, wrap="word",
        )
        textbox.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 12))
        textbox.insert("1.0", content)
        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="e", padx=22, pady=(0, 20))

        def copy_output():
            window.clipboard_clear()
            window.clipboard_append(textbox.get("1.0", "end-1c"))

        ctk.CTkButton(
            controls, text="COPY TO CLIPBOARD", fg_color=ACCENT,
            hover_color=ACCENT_HOVER, command=copy_output,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            controls, text="CLOSE", fg_color="#374151",
            hover_color="#475569", command=window.destroy,
        ).pack(side="left")

    def _export_selected_story_pack(self):
        story = self.selected_story
        if story is None:
            return
        destination = filedialog.asksaveasfilename(
            parent=self, title="Export Council story pack",
            initialfile=f"{self._safe_filename(story.title or 'Council-story')} - Story Pack.zip",
            defaultextension=".zip",
            filetypes=(("ZIP archive", "*.zip"), ("All files", "*.*")),
        )
        if not destination:
            return
        outputs = self._selected_publication_outputs()
        image_path = self._selected_image_path()
        metadata = {
            "title": story.title, "summary": story.summary,
            "source": story.source, "source_url": story.url,
            "published": self._format_date(story.published),
            "category": story.category, "priority": story.priority,
            "matched_locations": story.extras.get("matched_locations", []),
            "relevance_reason": story.extras.get("priority_reason", ""),
            "image_credit": self._selected_image_credit(story),
        }
        try:
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("website-article.txt", outputs["website"])
                archive.writestr("facebook-post.txt", outputs["facebook"])
                archive.writestr("newsletter-copy.txt", outputs["newsletter"])
                archive.writestr("article.txt", story.body)
                archive.writestr("summary.txt", story.summary)
                archive.writestr("source-link.txt", story.url)
                archive.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))
                if image_path is not None and not story.image_is_fallback:
                    archive.write(image_path, arcname=f"image{image_path.suffix.lower() or '.jpg'}")
            self.status_label.configure(text=f"Status: Story Pack exported to {destination}")
        except (OSError, zipfile.BadZipFile) as error:
            messagebox.showerror("Story Pack export failed", str(error), parent=self)

    def _update_statistics(self):
        self.stat_labels["total"].configure(text=str(len(self.stories)))
        now = datetime.now(timezone.utc)
        ages = []
        for story in self.stories:
            parsed = published_datetime(getattr(story, "published", ""))
            ages.append((now - parsed).days if parsed is not None else None)
        self.stat_labels["today"].configure(text=str(sum(age == 0 for age in ages)))
        self.stat_labels["recent"].configure(
            text=str(sum(age is not None and 1 <= age <= 3 for age in ages))
        )
        self.stat_labels["older"].configure(
            text=str(sum(age is None or age > 3 for age in ages))
        )
        self.stat_labels["selected"].configure(
            text="1" if self.selected_story is not None else "0"
        )


def open_council(master=None):
    """Open Council Intelligence."""
    return CouncilIntelligenceWindow(master)


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = ctk.CTk()
    app.withdraw()
    window = CouncilIntelligenceWindow(app)
    window.protocol("WM_DELETE_WINDOW", lambda: (window.destroy(), app.destroy()))
    app.mainloop()
