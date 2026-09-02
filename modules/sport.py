from pathlib import Path
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO
import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import webbrowser
import zipfile
from tkinter import filedialog, messagebox
from newsdesk.services.sport_article_service import SportArticleService
from modules.sport_source_manager import SportSourceManagerWindow

import customtkinter as ctk
from PIL import Image

from newsdesk.services.sport_collection import (
    SportCollectionService,
)
from newsdesk.action_bar import NewsDeskActionBar
from newsdesk.header import NewsDeskHeader
from newsdesk.social.selection import add_story_to_social_desk
from newsdesk.display_dates import format_uk_date
from newsdesk.story_queue import NewsDeskStoryQueue
from newsdesk.image_preview_cache import IMAGE_PREVIEW_CACHE
from newsdesk.theme import (
    ACCENT, ACCENT_HOVER, APP_BG, BORDER, BRAND_RED, BRAND_RED_HOVER,
    CARD_BG, HEADER_BG, IMMEDIATE, LOGO_PATH, PANEL_BG, ROUTINE, SUCCESS,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, URGENT,
    HEADER_HEIGHT, LOGO_SIZE,
)
from newsdesk.ui_support import (
    DEFAULT_SEARCH_DEBOUNCE_MS,
    DebouncedAction,
    IntelligenceWindowSupport,
    focus_existing_window,
    maximize_window,
)
from newsdesk.sports.sport_scraper import SportScraper
from newsdesk.feed_policy import prepare_lincolnshire_feed, published_datetime


LOGGER = logging.getLogger(__name__)

class SportIntelligenceWindow(ctk.CTkToplevel):
    """Sport Intelligence editorial workspace."""

    _SEARCH_DEBOUNCE_MS = DEFAULT_SEARCH_DEBOUNCE_MS

    ALL_SPORTS = "All sports"
    ALL_SOURCES = "All clubs and sources"
    ALL_AREAS = "All localities"
    DEFAULT_SORT = "Newest first"
    QUEUE_RENDER_LIMIT = 100

    AREA_FILTERS = (
        ALL_AREAS,
        "Lincolnshire",
        "North Lincolnshire",
        "North East Lincolnshire",
        "Regional Lincolnshire matches",
    )
    SORT_OPTIONS = (
        DEFAULT_SORT,
        "Oldest first",
        "Title A\u2013Z",
        "Title Z\u2013A",
    )

    def __init__(self, master=None):
        super().__init__(master)
        self._window_support = IntelligenceWindowSupport(self, master)
        self._window_support.install()

        self.title("Sport Intelligence - Devour Lincolnshire NewsDesk")
        self.geometry("1450x900")
        self.minsize(1150, 720)
        self.configure(fg_color=APP_BG)

        if master is not None:
            self.transient(master)

        self._window_support.call_later(100, lambda: maximize_window(self))

        self.stories = []
        self.publish_results = {}
        self.selected_story = None
        self.selected_result = None
        self.article_service = SportArticleService()
        self.is_refreshing = False
        self._visible_stories = []
        self._updating_filter_controls = False
        self._search_debounce = DebouncedAction(
            self._window_support,
            self._SEARCH_DEBOUNCE_MS,
            self._refresh_visible_queue,
        )
        self.source_manager_window = None

        self._build_layout()

    def _build_layout(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_statistics()
        self._build_workspace()
        self._build_status_bar()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self):
        self.header = NewsDeskHeader(
            self,
            module_title="Sport Intelligence",
            subtitle="Collect  •  Lincolnshire  •  Review  •  Publish",
            primary_button_text="REFRESH SPORT NEWS",
            primary_command=self._refresh_sport_news,
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
        self.source_manager_window = SportSourceManagerWindow(
            self,
            on_refresh=self._refresh_sport_news,
        )

    def _open_social_desk(self):
        from modules.social_desk import open_social_desk
        return open_social_desk(self)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _build_statistics(self):
        strip = ctk.CTkFrame(
            self,
            fg_color=APP_BG,
            corner_radius=0,
        )
        strip.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=24,
            pady=(18, 12),
        )

        for column in range(5):
            strip.grid_columnconfigure(column, weight=1, uniform="statistics")

        self.stat_labels = {}

        statistics = (
            ("today", "TODAY", "0", SUCCESS),
            ("recent", "PREVIOUS 3 DAYS", "0", TEXT_PRIMARY),
            ("older", "OLDER", "0", TEXT_MUTED),
            ("review", "SELECTED STORY", "0", ACCENT),
            ("total", "TOTAL STORIES", "0", SUCCESS),
        )

        for column, (key, title, value, colour) in enumerate(statistics):
            card = ctk.CTkFrame(
                strip,
                fg_color=CARD_BG,
                corner_radius=14,
                border_width=1,
                border_color=BORDER,
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=6,
            )

            ctk.CTkLabel(
                card,
                text=title,
                font=("Arial", 11, "bold"),
                text_color=TEXT_MUTED,
            ).pack(pady=(13, 3))

            value_label = ctk.CTkLabel(
                card,
                text=value,
                font=("Arial", 25, "bold"),
                text_color=colour,
            )
            value_label.pack(pady=(0, 13))

            self.stat_labels[key] = value_label

    # ------------------------------------------------------------------
    # Main workspace
    # ------------------------------------------------------------------

    def _build_workspace(self):
        workspace = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        workspace.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=30,
            pady=(4, 18),
        )

        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=2)
        workspace.grid_columnconfigure(1, weight=5)

        self._build_story_queue(workspace)
        self._build_editorial_review(workspace)

    # ------------------------------------------------------------------
    # Story queue
    # ------------------------------------------------------------------

    def _build_story_queue(self, parent):
        """
        Build the shared NewsDesk story queue.

        Sport-specific filtering and selection remain in this window, while
        the reusable component owns queue layout, rendering, counts and
        empty-state presentation.
        """

        queue_panel = ctk.CTkFrame(parent, fg_color="transparent")
        queue_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8),
        )
        queue_panel.grid_rowconfigure(1, weight=1)
        queue_panel.grid_columnconfigure(0, weight=1)

        self._build_queue_filter_controls(queue_panel)

        self.story_queue = NewsDeskStoryQueue(
            queue_panel,
            empty_title="No sport stories loaded.",
            empty_message=(
                "Select “Refresh Sport News” to collect the latest releases."
            ),
            on_filter_change=self._apply_filter,
            on_story_selected=self._handle_queue_story_selected,
        )
        self.story_queue.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.story_queue.filter_menu.grid_remove()

        # Temporary compatibility aliases for code that still reads the
        # filter control directly. These can disappear when the remaining
        self.queue_count_label = self.story_queue.queue_count_label

    def _build_queue_filter_controls(self, parent):
        controls = ctk.CTkFrame(
            parent,
            fg_color=HEADER_BG,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        controls.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        controls.grid_columnconfigure(0, weight=1)
        controls.grid_columnconfigure(1, weight=1)

        self.search_var = ctk.StringVar(value="")
        self.search_entry = ctk.CTkEntry(
            controls,
            textvariable=self.search_var,
            placeholder_text="Search title, club or sport...",
            height=32,
            fg_color=CARD_BG,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
        )
        self.search_entry.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(10, 5),
            pady=(10, 5),
        )

        self.reset_filters_button = ctk.CTkButton(
            controls,
            text="RESET FILTERS",
            height=32,
            width=110,
            fg_color="#374151",
            hover_color="#475569",
            command=self._reset_filter_controls,
        )
        self.reset_filters_button.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(5, 10),
            pady=(10, 5),
        )

        self.sport_filter_menu = self._queue_filter_menu(
            controls,
            label="Sport",
            values=(self.ALL_SPORTS,),
            row=1,
            column=0,
        )
        self.source_filter_menu = self._queue_filter_menu(
            controls,
            label="Club/source",
            values=(self.ALL_SOURCES,),
            row=1,
            column=1,
        )
        self.area_filter_menu = self._queue_filter_menu(
            controls,
            label="Locality",
            values=self.AREA_FILTERS,
            row=2,
            column=0,
        )
        self.sort_menu = self._queue_filter_menu(
            controls,
            label="Sort",
            values=self.SORT_OPTIONS,
            row=2,
            column=1,
            bottom_padding=10,
        )

        self.search_var.trace_add("write", self._on_search_changed)

    def _queue_filter_menu(
        self,
        parent,
        *,
        label,
        values,
        row,
        column,
        columnspan=1,
        bottom_padding=5,
    ):
        field = ctk.CTkFrame(parent, fg_color="transparent")
        field.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="ew",
            padx=(
                10 if column == 0 else 5,
                10 if columnspan > 1 or column == 1 else 5,
            ),
            pady=(0, bottom_padding),
        )
        field.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            field,
            text=label.upper(),
            height=14,
            font=("Arial", 9, "bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 2))

        menu = ctk.CTkOptionMenu(
            field,
            values=list(values),
            height=30,
            fg_color=CARD_BG,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=CARD_BG,
            dropdown_hover_color="#475569",
            dropdown_text_color=TEXT_PRIMARY,
            font=("Arial", 10),
            dropdown_font=("Arial", 11),
            command=lambda _value: self._refresh_visible_queue(),
        )
        menu.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        menu.set(values[0])
        return menu

    # ------------------------------------------------------------------
    # Editorial review
    # ------------------------------------------------------------------

    def _build_editorial_review(self, parent):
        review_panel = ctk.CTkFrame(
            parent,
            fg_color=HEADER_BG,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
        )
        review_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(8, 0),
        )

        review_panel.grid_rowconfigure(1, weight=1)
        review_panel.grid_columnconfigure(0, weight=1)

        heading = ctk.CTkFrame(
            review_panel,
            fg_color="transparent",
        )
        heading.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=22,
            pady=(17, 10),
        )

        ctk.CTkLabel(
            heading,
            text="STORY WORKSPACE",
            font=("Arial", 16, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self.selection_status_label = ctk.CTkLabel(
            heading,
            text="NO STORY SELECTED",
            font=("Arial", 11, "bold"),
            text_color=TEXT_MUTED,
        )
        self.selection_status_label.pack(side="right")

        self.review_content = ctk.CTkScrollableFrame(
            review_panel,
            fg_color=PANEL_BG,
            corner_radius=12,
        )
        self.review_content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(0, 10),
        )

        self.review_placeholder = ctk.CTkFrame(
            self.review_content,
            fg_color="transparent",
        )
        self.review_placeholder.pack(
            fill="both",
            expand=True,
            padx=40,
            pady=90,
        )

        ctk.CTkLabel(
            self.review_placeholder,
            text="SELECT A STORY",
            font=("Arial", 21, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            self.review_placeholder,
            text=(
                "Choose a sport story from the queue to view its summary,\n"
                "classification, priority score and editorial decision."
            ),
            font=("Arial", 13),
            text_color=TEXT_MUTED,
            justify="center",
        ).pack()

        self._build_action_bar(review_panel)

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------

    def _build_action_bar(self, parent):
        """Build the shared NewsDesk publishing action bar."""

        self.action_bar = NewsDeskActionBar(
            parent,
            command=self._run_action,
        )
        self.action_bar.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=12,
            pady=(0, 12),
        )

        # Preserve the existing public compatibility surface for callers that
        # access the action button mapping directly.
        self.action_buttons = self.action_bar.buttons

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self):
        status_bar = ctk.CTkFrame(
            self,
            fg_color=HEADER_BG,
            corner_radius=0,
            height=38,
        )
        status_bar.grid(
            row=3,
            column=0,
            sticky="ew",
        )
        status_bar.grid_propagate(False)
        status_bar.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status_bar,
            text="Status: Ready",
            font=("Arial", 11),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.status_label.grid(
            row=0,
            column=0,
            sticky="w",
            padx=22,
        )

        self.collection_progress = ctk.CTkProgressBar(
            status_bar,
            width=130,
            height=8,
            corner_radius=4,
            mode="indeterminate",
            progress_color=ACCENT,
            fg_color=CARD_BG,
        )
        self.collection_progress.grid(
            row=0,
            column=1,
            padx=(10, 4),
        )
        self.collection_progress.grid_remove()

        ctk.CTkLabel(
            status_bar,
            text="Sport Intelligence • Live NewsDesk",
            font=("Arial", 11),
            text_color=TEXT_MUTED,
        ).grid(
            row=0,
            column=2,
            sticky="e",
            padx=22,
        )

    # ------------------------------------------------------------------
    # Sport collection and queue
    # ------------------------------------------------------------------

    def _refresh_sport_news(self):
        if self.is_refreshing:
            return

        self.is_refreshing = True
        self.refresh_button.configure(
            state="disabled",
            text="COLLECTING...",
        )
        self.status_label.configure(
            text="Status: Collecting the latest Lincolnshire Sport reports..."
        )
        self.collection_progress.grid()
        self.collection_progress.start()

        worker = threading.Thread(
            target=self._collect_sport_news,
            daemon=True,
        )
        worker.start()

    def _collect_sport_news(self):
        try:
            service = SportCollectionService()
            collection = service.collect()

            stories = collection.stories
            results = collection.publish_results
            errors = collection.errors
            source_health = collection.source_health

            self.after(
                0,
                lambda: self.status_label.configure(
                    text=(
                        f"Status: Analysing {len(stories)} "
                        "collected sport stories..."
                    )
                ),
            )

            self._window_support.call_later_guarded(
                0,
                lambda: self._collection_complete(
                    stories,
                    results,
                    errors,
                    source_health=source_health,
                ),
                on_error=self._collection_failed,
            )

        except Exception as error:
            error_message = str(error)

            self.after(
                0,
                lambda message=error_message: self._collection_failed(message),
            )

    def _collection_complete(
        self,
        stories,
        results,
        errors,
        notify_dashboard=True,
        source_health=None,
    ):
        incoming_stories = list(stories)
        filtered_stories = SportScraper._filter_recent_stories(
            incoming_stories,
            stage="sport-ui-boundary",
        )
        kept_ids = {id(story) for story in filtered_stories}
        removed_count = len(incoming_stories) - len(filtered_stories)
        if removed_count:
            LOGGER.warning(
                "Sport UI safety boundary removed %d future-dated "
                "stories supplied by the collection layer.",
                removed_count,
            )

        self.publish_results = {
            story_id: result
            for story_id, result in dict(results).items()
            if story_id in kept_ids
        }
        self.stories = prepare_lincolnshire_feed(filtered_stories)
        retained_ids = {id(story) for story in self.stories}
        self.publish_results = {
            story_id: result
            for story_id, result in self.publish_results.items()
            if story_id in retained_ids
        }
        self.selected_story = None
        self.selected_result = None
        self.is_refreshing = False

        self.refresh_button.configure(
            state="normal",
            text="REFRESH SPORT NEWS",
        )
        self.collection_progress.stop()
        self.collection_progress.grid_remove()

        self._update_statistics()
        self._refresh_filter_options()
        self._refresh_visible_queue()
        self._show_review_placeholder()

        processed = len(self.publish_results)
        total = len(self.stories)

        health = list(source_health or [])
        yielding = sum(1 for row in health if row.get("status") == "yielding")
        reached = sum(1 for row in health if row.get("status") != "failed")
        failed = sum(1 for row in health if row.get("status") == "failed")
        health_text = (
            f" Sources: {yielding} yielding, {reached - yielding} with no stories, "
            f"{failed} failed."
            if health
            else ""
        )
        self.status_label.configure(
            text=(
                f"Status: Loaded {total} sport stories; "
                f"{processed} processed successfully.{health_text}"
            )
        )

        if notify_dashboard:
            self._window_support.notify_story_refresh(
                self.stories, self.publish_results, errors
            )

    def load_stories(self, stories, publish_results=None, errors=None):
        """Load a completed Home payload without collecting again."""

        self._collection_complete(
            list(stories), dict(publish_results or {}), list(errors or []),
            notify_dashboard=False,
        )
        self.status_label.configure(
            text=f"Status: Loaded {len(self.stories)} sport stories from NewsDesk Pro Home."
        )

    def _collection_failed(self, error_message):
        self.is_refreshing = False
        self.refresh_button.configure(
            state="normal",
            text="REFRESH SPORT NEWS",
        )
        self.collection_progress.stop()
        self.collection_progress.grid_remove()
        self.status_label.configure(
            text="Status: Sport news collection failed."
        )

        messagebox.showerror(
            "Sport collection failed",
            "The latest sport stories could not be collected.\n\n"
            f"{error_message}",
            parent=self,
        )

    def _apply_filter(self, selected_filter):
        self._refresh_visible_queue()

    def _on_search_changed(self, *_args):
        if not self._updating_filter_controls:
            self._search_debounce.schedule()

    def _refresh_filter_options(self):
        self._updating_filter_controls = True
        try:
            self._configure_filter_menu(
                self.sport_filter_menu,
                (self.ALL_SPORTS, *self._distinct_sport_values()),
                self.ALL_SPORTS,
            )
            self._configure_filter_menu(
                self.source_filter_menu,
                (self.ALL_SOURCES, *self._distinct_source_values()),
                self.ALL_SOURCES,
            )
        finally:
            self._updating_filter_controls = False

    @staticmethod
    def _configure_filter_menu(menu, values, default):
        current = menu.get()
        values = tuple(values)
        menu.configure(values=list(values))
        menu.set(current if current in values else default)

    def _distinct_sport_values(self):
        return self._distinct_casefolded_values(
            self._story_sport_value(story)
            for story in self.stories
        )

    def _distinct_source_values(self):
        return self._distinct_casefolded_values(
            self._story_source_value(story)
            for story in self.stories
        )

    @staticmethod
    def _distinct_casefolded_values(values):
        distinct = {}
        for value in values:
            cleaned = str(value or "").strip()
            if cleaned:
                distinct.setdefault(cleaned.casefold(), cleaned)
        return tuple(sorted(distinct.values(), key=str.casefold))

    @staticmethod
    def _story_extras(story):
        extras = getattr(story, "extras", {})
        return extras if isinstance(extras, dict) else {}

    def _story_sport_value(self, story):
        extras = self._story_extras(story)
        return str(
            extras.get("sport")
            or getattr(story, "category", "")
            or ""
        ).strip()

    def _story_source_value(self, story):
        extras = self._story_extras(story)
        return str(
            extras.get("source_organisation")
            or extras.get("organisation")
            or getattr(story, "source", "")
            or ""
        ).strip()

    def _story_searchable_text(self, story):
        extras = self._story_extras(story)
        tags = getattr(story, "tags", ()) or ()
        if isinstance(tags, str):
            tags = (tags,)
        values = (
            getattr(story, "title", ""),
            getattr(story, "source", ""),
            extras.get("source_organisation", ""),
            extras.get("organisation", ""),
            self._story_sport_value(story),
            " ".join(str(tag) for tag in tags),
            getattr(story, "location", ""),
            extras.get("editorial_zone", ""),
            extras.get("editorial_zone_label", ""),
            extras.get("matched_place", ""),
            getattr(story, "summary", ""),
        )
        return " ".join(str(value or "") for value in values).casefold()

    def _combined_filtered_stories(self):
        query = self.search_var.get().strip().casefold()
        selected_sport = self.sport_filter_menu.get()
        selected_source = self.source_filter_menu.get()
        selected_area = self.area_filter_menu.get()

        visible = []
        for story in self.stories:
            if query and query not in self._story_searchable_text(story):
                continue
            if (
                selected_sport != self.ALL_SPORTS
                and self._story_sport_value(story).casefold()
                != selected_sport.casefold()
            ):
                continue
            if (
                selected_source != self.ALL_SOURCES
                and self._story_source_value(story).casefold()
                != selected_source.casefold()
            ):
                continue
            if selected_area != self.ALL_AREAS:
                extras = self._story_extras(story)
                location_text = " ".join(
                    str(value or "")
                    for value in (
                        getattr(story, "location", ""),
                        extras.get("location", ""),
                        extras.get("geographic_matches", ""),
                    )
                ).casefold()
                if selected_area == "Regional Lincolnshire matches":
                    if not extras.get("geographic_filter"):
                        continue
                elif selected_area.casefold() not in location_text:
                    continue
            visible.append(story)
        return visible

    def _stable_sorted_stories(self, stories):
        stories = list(stories)
        selected_sort = self.sort_menu.get()

        if selected_sort == "Newest first":
            return sorted(
                stories,
                key=lambda story: (
                    self._published_timestamp(story) is not None,
                    self._published_timestamp(story) or 0.0,
                ),
                reverse=True,
            )
        if selected_sort == "Oldest first":
            return sorted(
                stories,
                key=lambda story: (
                    self._published_timestamp(story) is None,
                    self._published_timestamp(story) or 0.0,
                ),
            )
        if selected_sort == "Title A\u2013Z":
            return sorted(
                stories,
                key=lambda story: str(story.title or "").casefold(),
            )
        if selected_sort == "Title Z\u2013A":
            return sorted(
                stories,
                key=lambda story: str(story.title or "").casefold(),
                reverse=True,
            )
        return stories

    @staticmethod
    def _published_timestamp(story):
        value = str(getattr(story, "published", "") or "").strip()
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()

    def _reset_filter_controls(self):
        self._updating_filter_controls = True
        try:
            self.search_var.set("")
            self.sport_filter_menu.set(self.ALL_SPORTS)
            self.source_filter_menu.set(self.ALL_SOURCES)
            self.area_filter_menu.set(self.ALL_AREAS)
            self.sort_menu.set(self.DEFAULT_SORT)
        finally:
            self._updating_filter_controls = False
        self._refresh_visible_queue()

    def _refresh_visible_queue(self):
        self._search_debounce.cancel()
        visible_stories = self._stable_sorted_stories(
            self._combined_filtered_stories()
        )
        self._visible_stories = visible_stories

        selected_story = self.selected_story
        selected_is_visible = selected_story is not None and any(
            story is selected_story for story in visible_stories
        )
        if selected_story is not None and not selected_is_visible:
            self.selected_story = None
            self.selected_result = None
            self._show_review_placeholder()

        self._populate_story_queue(visible_stories)
        if selected_is_visible:
            self.story_queue._selected_story_id = id(selected_story)

        self.status_label.configure(
            text=(
                f"Status: Showing {len(visible_stories)} of "
                f"{len(self.stories)} sport stories."
            )
        )

    def _populate_story_queue(self, stories):
        """
        Convert Sport Story objects into the shared queue's mapping format.
        """

        if self.stories:
            self.story_queue.set_empty_state(
                title="No stories match the current search and filters.",
                message="Adjust the controls or select Reset Filters.",
            )
        else:
            self.story_queue.set_empty_state(
                title="No sport stories loaded.",
                message=(
                    "Select “Refresh Sport News” to collect the latest releases."
                ),
            )

        displayed_stories = list(stories)[:self.QUEUE_RENDER_LIMIT]
        self.story_queue.set_stories(
            self._queue_story_mapping(story)
            for story in displayed_stories
        )
        visible_count = len(stories)
        total_count = len(self.stories)
        noun = "story" if total_count == 1 else "stories"
        if visible_count > len(displayed_stories):
            count_text = (
                f"Showing {len(displayed_stories)} of {visible_count} matching "
                f"({total_count} total)"
            )
        else:
            count_text = f"{visible_count} of {total_count} {noun}"
        self.queue_count_label.configure(text=count_text)

    def _queue_story_mapping(self, story):
        """
        Adapt one Sport Story for the reusable NewsDeskStoryQueue.
        """

        location = str(
            getattr(story, "location", "")
            or ""
        ).strip()
        source = str(
            getattr(story, "source", "")
            or ""
        ).strip()
        published = format_uk_date(getattr(story, "published", ""))
        queue_source = location or source

        return {
            "id": id(story),
            "title": story.title or "Untitled sport story",
            "summary": story.summary or "",
            "priority": "",
            "source": queue_source,
            "published": published,
            "story": story,
        }

    def _handle_queue_story_selected(self, queue_story):
        """
        Resolve a shared-queue mapping back to its Sport Story object.
        """

        story = queue_story.get("story")

        if story is not None:
            self._select_story(story)

    # ------------------------------------------------------------------
    # Story workspace
    # ------------------------------------------------------------------

    def _select_story(self, story):

        try:
            if self.article_service.needs_enrichment(story):

                self.status_label.configure(
                    text="Status: Downloading full article..."
                )

                result = self.article_service.enrich(story)

                if result.successful:
                    self.publish_results[id(story)] = result.publish_result

        except Exception as error:
            LOGGER.exception("Article enrichment failed: %s", error)

        self.selected_story = story
        self.selected_result = self.publish_results.get(id(story))

        self._clear_review_content()
        self._reset_workspace_scroll()



        self.selection_status_label.configure(text="LINCOLNSHIRE")
        self.stat_labels["review"].configure(text="1")

        self._workspace_label(
            story.title or "Untitled sport story",
            font=("Arial", 22, "bold"),
            colour=TEXT_PRIMARY,
        )

        metadata = " • ".join(
            value
            for value in (
                str(story.source or "").strip(),
                format_uk_date(story.published),
            )
            if value
        )

        if metadata:
            self._workspace_label(
                metadata,
                font=("Arial", 11, "bold"),
                colour=TEXT_MUTED,
                pady=(5, 18),
            )

        self._workspace_image(story)

        summary = str(story.summary or "").strip()
        if summary:
            self._workspace_section("SUMMARY", summary)

        self._workspace_section(
            "ARTICLE",
            str(story.body or "No article text was collected.").strip(),
        )

        classification = str(story.classification or "").strip()
        decision = str(story.editorial_decision or "").strip()
        tags = ", ".join(story.tags or [])
        extras = getattr(story, "extras", {}) or {}
        editorial_parts = []
        if classification:
            editorial_parts.append(f"Classification: {classification}")
        if decision:
            editorial_parts.append(f"Editorial decision: {decision}")
        if tags:
            editorial_parts.append(f"Tags: {tags}")

        if editorial_parts:
            self._workspace_section(
                "STORY INFORMATION",
                "\n\n".join(editorial_parts),
            )

        for button in self.action_buttons.values():
            button.configure(state="normal")

        self.status_label.configure(
            text=f"Status: Selected — {story.title}"
        )

    def _show_review_placeholder(self):
        self._clear_review_content()
        self.selection_status_label.configure(text="NO STORY SELECTED")
        self.stat_labels["review"].configure(text="0")

        placeholder = ctk.CTkFrame(
            self.review_content,
            fg_color="transparent",
        )
        placeholder.pack(
            fill="both",
            expand=True,
            padx=40,
            pady=90,
        )

        ctk.CTkLabel(
            placeholder,
            text="SELECT A STORY",
            font=("Arial", 21, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            placeholder,
            text=(
                "Choose a sport story from the queue to view its summary,\n"
                "classification, priority and publishing outputs."
            ),
            font=("Arial", 13),
            text_color=TEXT_MUTED,
            justify="center",
        ).pack()

        for button in self.action_buttons.values():
            button.configure(state="disabled")

    def _clear_review_content(self):
        for widget in self.review_content.winfo_children():
            widget.destroy()

    def _reset_workspace_scroll(self):
        canvas = getattr(self.review_content, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0)

    def _workspace_image(self, story):
        """
        Display the locally cached story image without passing image bytes
        through StoryEngine.

        The preview is created only for the currently selected story and is
        resized before CustomTkinter receives it, keeping memory use bounded.
        """

        local_path = str(
            getattr(story, "image_local_path", "") or ""
        ).strip()

        if not local_path:
            return

        image_path = Path(local_path)

        if not image_path.is_file():
            return

        preview_image = IMAGE_PREVIEW_CACHE.get(
            image_path,
            (720, 405),
            allow_upscale=True,
        )
        if preview_image is None:
            return

        width, height = preview_image.size

        if width <= 0 or height <= 0:
            return

        image_frame = ctk.CTkFrame(
            self.review_content,
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER,
            corner_radius=10,
        )
        image_frame.pack(
            fill="x",
            padx=22,
            pady=(0, 14),
        )

        ctk_image = ctk.CTkImage(
            light_image=preview_image,
            dark_image=preview_image,
            size=(width, height),
        )

        image_label = ctk.CTkLabel(
            image_frame,
            text="",
            image=ctk_image,
            fg_color="transparent",
        )
        image_label.image = ctk_image
        image_label.pack(
            padx=10,
            pady=10,
        )

        caption = str(
            getattr(story, "image_caption", "") or ""
        ).strip()
        credit = self._selected_image_credit(story)

        if caption:
            ctk.CTkLabel(
                image_frame,
                text=caption,
                font=("Arial", 10),
                text_color=TEXT_MUTED,
                justify="left",
                anchor="w",
                wraplength=860,
            ).pack(
                fill="x",
                padx=12,
                pady=(0, 4),
            )

        ctk.CTkLabel(
            image_frame,
            text=f"Image credit: {credit}",
            font=("Arial", 10, "bold"),
            text_color=TEXT_SECONDARY,
            justify="left",
            anchor="w",
            wraplength=860,
        ).pack(
            fill="x",
            padx=12,
            pady=(0, 4),
        )

        image_details = self._image_quality_details(story, image_path)

        ctk.CTkLabel(
            image_frame,
            text=image_details["display"],
            font=("Arial", 9),
            text_color=TEXT_MUTED,
            justify="left",
            anchor="w",
            wraplength=860,
        ).pack(
            fill="x",
            padx=12,
            pady=(0, 10),
        )

        actions = ctk.CTkFrame(
            image_frame,
            fg_color="transparent",
        )
        actions.pack(
            fill="x",
            padx=10,
            pady=(0, 10),
        )

        image_actions = (
            ("COPY IMAGE", self._copy_selected_image),
            ("COPY CREDIT", self._copy_selected_image_credit),
            ("SAVE IMAGE AS...", self._save_selected_image),
            ("OPEN IMAGE", self._open_selected_image),
            ("SHOW IN FOLDER", self._show_selected_image_folder),
            ("STORY PACK", self._export_selected_story_pack),
        )

        for column, (label, command) in enumerate(image_actions):
            actions.grid_columnconfigure(column, weight=1)
            ctk.CTkButton(
                actions,
                text=label,
                command=command,
                height=34,
                corner_radius=8,
                fg_color=BORDER,
                hover_color="#475569",
                text_color=TEXT_PRIMARY,
                font=("Arial", 10, "bold"),
            ).grid(
                row=0,
                column=column,
                sticky="ew",
                padx=4,
            )

    def _selected_image_path(self):
        """Return the selected story image path when it exists."""

        if self.selected_story is None:
            return None

        value = str(
            getattr(self.selected_story, "image_local_path", "") or ""
        ).strip()

        if not value:
            return None

        path = Path(value)
        return path if path.is_file() else None

    def _selected_image_credit(self, story=None):
        """Return the most specific available image credit."""

        current_story = story or self.selected_story

        if current_story is None:
            return "Devour Lincolnshire Sport"

        credit = str(
            getattr(current_story, "image_credit", "") or ""
        ).strip()

        if credit:
            return credit

        source = str(
            getattr(current_story, "source", "") or ""
        ).strip()

        return source or "Devour Lincolnshire Sport"

    def _copy_selected_image(self):
        """Copy the selected image itself to the Windows clipboard."""

        image_path = self._selected_image_path()

        if image_path is None:
            messagebox.showwarning(
                "Image unavailable",
                "The selected story does not have a local image.",
                parent=self,
            )
            return

        try:
            with Image.open(image_path) as source_image:
                clipboard_image = source_image.convert("RGB")
                output = BytesIO()
                clipboard_image.save(output, format="BMP")
                dib_data = output.getvalue()[14:]

            CF_DIB = 8
            GMEM_MOVEABLE = 0x0002

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            user32.OpenClipboard.argtypes = [wintypes.HWND]
            user32.OpenClipboard.restype = wintypes.BOOL
            user32.EmptyClipboard.argtypes = []
            user32.EmptyClipboard.restype = wintypes.BOOL
            user32.SetClipboardData.argtypes = [
                wintypes.UINT,
                wintypes.HANDLE,
            ]
            user32.SetClipboardData.restype = wintypes.HANDLE
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = wintypes.BOOL

            kernel32.GlobalAlloc.argtypes = [
                wintypes.UINT,
                ctypes.c_size_t,
            ]
            kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
            kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalUnlock.restype = wintypes.BOOL
            kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalFree.restype = wintypes.HGLOBAL

            if not user32.OpenClipboard(None):
                raise ctypes.WinError(ctypes.get_last_error())

            memory_handle = None

            try:
                if not user32.EmptyClipboard():
                    raise ctypes.WinError(ctypes.get_last_error())

                memory_handle = kernel32.GlobalAlloc(
                    GMEM_MOVEABLE,
                    len(dib_data),
                )

                if not memory_handle:
                    raise ctypes.WinError(ctypes.get_last_error())

                memory_pointer = kernel32.GlobalLock(memory_handle)

                if not memory_pointer:
                    raise ctypes.WinError(ctypes.get_last_error())

                try:
                    ctypes.memmove(
                        memory_pointer,
                        dib_data,
                        len(dib_data),
                    )
                finally:
                    kernel32.GlobalUnlock(memory_handle)

                clipboard_handle = user32.SetClipboardData(
                    CF_DIB,
                    memory_handle,
                )

                if not clipboard_handle:
                    raise ctypes.WinError(ctypes.get_last_error())

                # Ownership transfers to Windows after SetClipboardData.
                memory_handle = None

            finally:
                user32.CloseClipboard()

                if memory_handle:
                    kernel32.GlobalFree(memory_handle)

            self.status_label.configure(
                text="Status: Image copied to clipboard."
            )

        except Exception as error:
            messagebox.showerror(
                "Copy image failed",
                f"The image could not be copied.\n\n{error}",
                parent=self,
            )

    def _copy_selected_image_credit(self):
        """Copy a publication-ready image credit to the text clipboard."""

        if self.selected_story is None:
            return

        credit_text = (
            f"Image credit: "
            f"{self._selected_image_credit(self.selected_story)}"
        )

        try:
            self.clipboard_clear()
            self.clipboard_append(credit_text)
            self.update_idletasks()
            self.status_label.configure(
                text=f"Status: Copied — {credit_text}"
            )
        except Exception as error:
            messagebox.showerror(
                "Copy credit failed",
                f"The image credit could not be copied.\n\n{error}",
                parent=self,
            )

    def _save_selected_image(self):
        """Save a copy of the selected image to a chosen location."""

        image_path = self._selected_image_path()

        if image_path is None:
            messagebox.showwarning(
                "Image unavailable",
                "The selected story does not have a local image.",
                parent=self,
            )
            return

        suffix = image_path.suffix or ".jpg"
        title = self._safe_filename(
            getattr(self.selected_story, "title", "sport-story-image")
        )

        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Save story image as",
            initialfile=f"{title}{suffix}",
            defaultextension=suffix,
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp *.gif"),
                ("All files", "*.*"),
            ],
        )

        if not destination:
            return

        try:
            shutil.copy2(image_path, destination)
            self.status_label.configure(
                text=f"Status: Image saved to {destination}"
            )
        except OSError as error:
            messagebox.showerror(
                "Save image failed",
                f"The image could not be saved.\n\n{error}",
                parent=self,
            )

    def _open_selected_image(self):
        """Open the selected image in the Windows default image viewer."""

        image_path = self._selected_image_path()

        if image_path is None:
            messagebox.showwarning(
                "Image unavailable",
                "The selected story does not have a local image.",
                parent=self,
            )
            return

        try:
            os.startfile(image_path)
            self.status_label.configure(
                text="Status: Image opened in the default viewer."
            )
        except OSError as error:
            messagebox.showerror(
                "Open image failed",
                f"The image could not be opened.\n\n{error}",
                parent=self,
            )

    def _show_selected_image_folder(self):
        """Open File Explorer with the selected image highlighted."""

        image_path = self._selected_image_path()

        if image_path is None:
            messagebox.showwarning(
                "Image unavailable",
                "The selected story does not have a local image.",
                parent=self,
            )
            return

        try:
            subprocess.Popen([
                "explorer",
                "/select,",
                str(image_path),
            ])
            self.status_label.configure(
                text="Status: Image shown in File Explorer."
            )
        except OSError as error:
            messagebox.showerror(
                "Open folder failed",
                f"File Explorer could not be opened.\n\n{error}",
                parent=self,
            )

    @staticmethod
    def _safe_filename(value):
        """Create a Windows-safe filename stem from a story title."""

        cleaned = "".join(
            character if character not in '<>:"/\\|?*' else "-"
            for character in str(value or "")
        )
        cleaned = " ".join(cleaned.split()).strip(" .-")
        return cleaned[:120] or "sport-story-image"

    def _image_quality_details(self, story, image_path):
        """Return lightweight quality and duplicate/cache information."""

        width = 0
        height = 0
        file_size = 0
        digest = ""

        try:
            file_size = image_path.stat().st_size

            with Image.open(image_path) as source_image:
                width, height = source_image.size

            hasher = hashlib.sha256()
            with image_path.open("rb") as image_file:
                for chunk in iter(lambda: image_file.read(131072), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()

        except (OSError, ValueError):
            pass

        megapixels = (width * height) / 1_000_000 if width and height else 0.0
        aspect_ratio = width / height if height else 0.0

        score = 0
        reasons = []

        if width >= 1600:
            score += 40
            reasons.append("high resolution")
        elif width >= 1200:
            score += 32
            reasons.append("good resolution")
        elif width >= 800:
            score += 24
            reasons.append("web resolution")
        elif width:
            score += 10
            reasons.append("small image")

        if height >= 600:
            score += 25
        elif height >= 400:
            score += 18
        elif height:
            score += 8

        if 1.35 <= aspect_ratio <= 2.1:
            score += 20
            reasons.append("strong editorial aspect")
        elif aspect_ratio:
            score += 10

        if file_size >= 150_000:
            score += 15
        elif file_size >= 50_000:
            score += 10
        elif file_size:
            score += 5

        score = min(100, score)

        if score >= 80:
            rating = "Excellent"
        elif score >= 65:
            rating = "Good"
        elif score >= 45:
            rating = "Usable"
        else:
            rating = "Low"

        duplicate_count = 0
        if digest:
            for candidate in self.stories:
                candidate_path = str(
                    getattr(candidate, "image_local_path", "") or ""
                ).strip()

                if not candidate_path:
                    continue

                candidate_file = Path(candidate_path)
                if not candidate_file.is_file():
                    continue

                try:
                    candidate_hasher = hashlib.sha256()
                    with candidate_file.open("rb") as candidate_stream:
                        for chunk in iter(
                            lambda: candidate_stream.read(131072),
                            b"",
                        ):
                            candidate_hasher.update(chunk)

                    if candidate_hasher.hexdigest() == digest:
                        duplicate_count += 1
                except OSError:
                    continue

        cache_label = (
            "cache reused"
            if bool(getattr(story, "image_cached", False))
            else "new download"
        )
        duplicate_label = (
            f" • used by {duplicate_count} stories"
            if duplicate_count > 1
            else ""
        )

        display = (
            f"Image quality: {rating} ({score}/100) • "
            f"{width}×{height}px • {megapixels:.2f}MP • "
            f"{file_size / 1024:.0f}KB • {cache_label}"
            f"{duplicate_label}"
        )

        return {
            "score": score,
            "rating": rating,
            "width": width,
            "height": height,
            "megapixels": round(megapixels, 2),
            "aspect_ratio": round(aspect_ratio, 3),
            "file_size_bytes": file_size,
            "sha256": digest,
            "duplicate_story_count": duplicate_count,
            "cache_reused": bool(
                getattr(story, "image_cached", False)
            ),
            "reasons": reasons,
            "display": display,
        }

    def _with_image_credit(self, output, *, channel):
        """Append a publication-ready image credit once."""

        text = str(output or "").strip()

        if not text or self.selected_story is None:
            return text

        credit = self._selected_image_credit(self.selected_story)
        credit_line = (
            f"📷 Image: {credit}"
            if channel in {"facebook", "newsletter"}
            else f"Image credit: {credit}"
        )

        if credit.casefold() in text.casefold():
            return text

        return f"{text}\n\n{credit_line}".strip()

    def _selected_publication_outputs(self):
        """Return credited outputs for the selected Story Pack."""

        result = self.selected_result
        outputs = {
            "website": "",
            "facebook": "",
            "newsletter": "",
        }

        if result is not None:
            for channel in outputs:
                value = str(
                    getattr(result, channel, "") or ""
                ).strip()

                if value:
                    outputs[channel] = self._with_image_credit(
                        value,
                        channel=channel,
                    )

        story = self.selected_story
        if story is None:
            return outputs

        if not outputs["website"]:
            outputs["website"] = self._with_image_credit(
                self._build_website_article(story),
                channel="website",
            )
        if not outputs["facebook"]:
            outputs["facebook"] = self._with_image_credit(
                self._build_facebook_post(story),
                channel="facebook",
            )
        if not outputs["newsletter"]:
            outputs["newsletter"] = self._with_image_credit(
                self._build_newsletter_copy(story),
                channel="newsletter",
            )

        return outputs

    def _export_selected_story_pack(self):
        """Create a ZIP containing image, copy, credits and metadata."""

        story = self.selected_story

        if story is None:
            return

        image_path = self._selected_image_path()
        safe_title = self._safe_filename(
            getattr(story, "title", "") or "sport-story"
        )

        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Export Sport story pack",
            initialfile=f"{safe_title} - Story Pack.zip",
            defaultextension=".zip",
            filetypes=[
                ("ZIP archive", "*.zip"),
                ("All files", "*.*"),
            ],
        )

        if not destination:
            return

        outputs = self._selected_publication_outputs()
        credit = self._selected_image_credit(story)
        quality = (
            self._image_quality_details(story, image_path)
            if image_path is not None
            else {
                "score": 0,
                "rating": "Unavailable",
                "width": 0,
                "height": 0,
                "megapixels": 0,
                "aspect_ratio": 0,
                "file_size_bytes": 0,
                "sha256": "",
                "duplicate_story_count": 0,
                "cache_reused": False,
                "reasons": [],
            }
        )

        extras = getattr(story, "extras", {}) or {}
        metadata = {
            "title": str(getattr(story, "title", "") or ""),
            "source": str(getattr(story, "source", "") or ""),
            "source_url": str(getattr(story, "url", "") or ""),
            "published": str(getattr(story, "published", "") or ""),
            "classification": str(
                getattr(story, "classification", "") or ""
            ),
            "editorial_decision": str(
                getattr(story, "editorial_decision", "") or ""
            ),
            "tags": list(getattr(story, "tags", []) or []),
            "image": {
                "source_url": str(
                    getattr(story, "image_url", "") or ""
                ),
                "caption": str(
                    getattr(story, "image_caption", "") or ""
                ),
                "credit": credit,
                "alt_text": str(
                    getattr(story, "image_alt_text", "") or ""
                ),
                "is_fallback": bool(
                    getattr(story, "image_is_fallback", False)
                ),
                "quality": quality,
            },
            "geography": {
                "matches": extras.get("geographic_matches", []),
                "location": getattr(story, "location", ""),
            },
        }

        image_details = [
            f"Image credit: {credit}",
            (
                f"Caption: "
                f"{getattr(story, 'image_caption', '') or '(none)'}"
            ),
            (
                f"Alt text: "
                f"{getattr(story, 'image_alt_text', '') or '(none)'}"
            ),
            (
                f"Original image URL: "
                f"{getattr(story, 'image_url', '') or '(none)'}"
            ),
            f"Quality: {quality['rating']} ({quality['score']}/100)",
            (
                f"Dimensions: {quality['width']}×"
                f"{quality['height']} pixels"
            ),
            (
                f"Cache reused: "
                f"{'Yes' if quality['cache_reused'] else 'No'}"
            ),
        ]

        try:
            with zipfile.ZipFile(
                destination,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.writestr(
                    "website-article.txt",
                    outputs["website"],
                )
                archive.writestr(
                    "facebook-post.txt",
                    outputs["facebook"],
                )
                archive.writestr(
                    "newsletter-copy.txt",
                    outputs["newsletter"],
                )
                archive.writestr(
                    "image-details.txt",
                    "\n".join(image_details),
                )
                archive.writestr(
                    "source-link.txt",
                    str(getattr(story, "url", "") or ""),
                )
                archive.writestr(
                    "metadata.json",
                    json.dumps(
                        metadata,
                        indent=2,
                        ensure_ascii=False,
                        default=str,
                    ),
                )

                if image_path is not None:
                    image_name = (
                        f"image{image_path.suffix.lower() or '.jpg'}"
                    )
                    archive.write(
                        image_path,
                        arcname=image_name,
                    )

            self.status_label.configure(
                text=f"Status: Story Pack exported to {destination}"
            )
            messagebox.showinfo(
                "Story Pack exported",
                (
                    "The Sport Story Pack has been created successfully.\n\n"
                    f"{destination}"
                ),
                parent=self,
            )

        except (OSError, zipfile.BadZipFile) as error:
            messagebox.showerror(
                "Story Pack export failed",
                (
                    "The Story Pack could not be created.\n\n"
                    f"{error}"
                ),
                parent=self,
            )

    def _workspace_label(
        self,
        text,
        *,
        font,
        colour,
        pady=(0, 0),
    ):
        ctk.CTkLabel(
            self.review_content,
            text=text,
            font=font,
            text_color=colour,
            justify="left",
            anchor="w",
            wraplength=820,
        ).pack(
            fill="x",
            padx=22,
            pady=pady,
            anchor="w",
        )

    def _workspace_section(self, heading, content):
        self._workspace_label(
            heading,
            font=("Arial", 11, "bold"),
            colour=ACCENT,
            pady=(8, 5),
        )

        textbox = ctk.CTkTextbox(
            self.review_content,
            height=max(110, min(320, 45 + len(content) // 4)),
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER,
            corner_radius=10,
            text_color=TEXT_SECONDARY,
            font=("Arial", 12),
            wrap="word",
        )
        textbox.pack(
            fill="x",
            padx=22,
            pady=(0, 12),
        )
        textbox.insert("1.0", content)
        textbox.configure(state="disabled")

    # ------------------------------------------------------------------
    # Publishing actions
    # ------------------------------------------------------------------

    def _run_action(self, action_name):
        """
        Open the selected story's generated publishing output.

        Website, Facebook and newsletter content come directly from the
        PublishResult created by StoryEngine. This keeps all publication
        formatting in newsdesk.formatters rather than rebuilding copy inside
        the Sport module.
        """

        if self.selected_story is None:
            return

        if action_name == "ADD TO NEWSLETTER":
            open_newsletter_action(
                self, self.selected_story, module_key="sport",
                newsletter_copy=str(
                    getattr(self.selected_result, "website", "") or ""
                ).strip(),
                on_changed=lambda: configure_newsletter_action(
                    self.action_bar, self.selected_story,
                ),
            )
            return

        if action_name == "ADD TO SOCIALS":
            add_story_to_social_desk(
                self, self.selected_story, module_key="sport",
            )
            return

        if action_name == "OPEN SOURCE":
            url = str(self.selected_story.url or "").strip()

            if not url:
                messagebox.showinfo(
                    "No source URL",
                    "This story does not contain a source URL.",
                    parent=self,
                )
                return

            webbrowser.open(url)

            self.status_label.configure(
                text="Status: Source opened in browser."
            )
            return

        result = self.selected_result

        if result is None:
            messagebox.showwarning(
                "Publishing output unavailable",
                (
                    "No publishing result was generated for this story.\n\n"
                    "Refresh the Sport News feed and try again."
                ),
                parent=self,
            )
            return

        output_fields = {
            "WEBSITE ARTICLE": "website",
            "FACEBOOK POST": "facebook",
            "NEWSLETTER COPY": "newsletter",
        }

        field_name = output_fields.get(action_name)

        if field_name is None:
            return

        output = str(
            getattr(result, field_name, "")
            or ""
        ).strip()

        if output:
            output = self._with_image_credit(
                output,
                channel=field_name,
            )

        if not output:
            extras = getattr(result, "extras", {}) or {}

            formatter_errors = (
                extras.get("formatter_errors", {})
                or {}
            )

            error_message = str(
                formatter_errors.get(field_name, "")
                or ""
            ).strip()

            message = (
                f"No {action_name.lower()} was generated for this story."
            )

            if error_message:
                message += (
                    f"\n\nFormatter error:\n{error_message}"
                )

            messagebox.showwarning(
                "No publishing output",
                message,
                parent=self,
            )
            return

        self._show_output_window(
            action_name,
            output,
        )

        self.status_label.configure(
            text=f"Status: Opened {action_name.title()}."
        )

    @staticmethod
    def _clean_copy(value):
        return " ".join(str(value or "").split())

    def _story_location(self, story):
        extras = getattr(story, "extras", {}) or {}
        return self._clean_copy(
            extras.get("matched_place")
            or extras.get("location")
            or getattr(story, "location", "")
            or extras.get("area")
        )

    def _story_category(self, story):
        extras = getattr(story, "extras", {}) or {}
        return self._clean_copy(
            extras.get("category")
            or getattr(story, "classification", "")
            or "Sport News"
        )

    def _body_paragraphs(self, story):
        body = str(story.body or "").strip()
        return [part.strip() for part in body.split("\n") if part.strip()]

    def _build_website_article(self, story):
        headline = self._clean_copy(story.title) or "Sport update"
        summary = self._clean_copy(story.summary)
        body = str(story.body or "").strip()
        source = self._clean_copy(story.source) or "Devour Lincolnshire Sport"
        published = self._clean_copy(story.published)
        location = self._story_location(story)

        lines = [headline, ""]
        if summary:
            lines.extend([summary, ""])
        if body:
            lines.extend([body, ""])
        details = [f"Source: {source}"]
        if location:
            details.append(f"Area: {location}")
        if published:
            details.append(f"Published: {published}")
        lines.append(" | ".join(details))
        return "\n".join(lines).strip()

    def _build_facebook_post(self, story):
        headline = self._clean_copy(story.title) or "Sport update"
        summary = self._clean_copy(story.summary)
        paragraphs = self._body_paragraphs(story)
        location = self._story_location(story)
        category = self._story_category(story)
        source = self._clean_copy(story.source) or "Devour Lincolnshire Sport"

        intro = summary or (self._clean_copy(paragraphs[0]) if paragraphs else "Further details have been reported by the source.")
        if len(intro) > 420:
            intro = intro[:417].rstrip() + "..."

        details = []
        if location:
            details.append(f"📍 {location}")
        if category:
            details.append(f"⚽ {category}")

        return (
            f"⚽ {headline}\n\n"
            f"{intro}\n\n"
            + ("\n".join(details) + "\n\n" if details else "")
            + f"📰 Read the full story for further details.\n\n"
            f"ℹ️ Source: {source}"
        )

    def _build_newsletter_copy(self, story):
        headline = self._clean_copy(story.title) or "Sport update"
        summary = self._clean_copy(story.summary)
        paragraphs = self._body_paragraphs(story)
        location = self._story_location(story)
        category = self._story_category(story)
        score = self._story_score(story)

        copy = summary or (self._clean_copy(paragraphs[0]) if paragraphs else "Devour Lincolnshire Sport has published a new update.")
        if len(copy) > 650:
            copy = copy[:647].rstrip() + "..."

        context = []
        if location:
            context.append(location)
        if category:
            context.append(category)
        context.append(f"NewsDesk score: {score}")

        return f"{headline}\n\n{copy}\n\n{' • '.join(context)}"

    def _show_output_window(self, title, content):
        window = ctk.CTkToplevel(self)
        window.title(f"{title.title()} - Sport Intelligence")
        window.geometry("900x700")
        window.minsize(650, 480)
        window.configure(fg_color=APP_BG)
        window.transient(self)
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            window,
            text=title,
            font=("Arial", 19, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=22,
            pady=(20, 12),
        )

        textbox = ctk.CTkTextbox(
            window,
            fg_color=PANEL_BG,
            border_width=1,
            border_color=BORDER,
            corner_radius=12,
            text_color=TEXT_PRIMARY,
            font=("Arial", 13),
            wrap="word",
        )
        textbox.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=22,
            pady=(0, 12),
        )
        textbox.insert("1.0", content or "No output was generated.")

        controls = ctk.CTkFrame(window, fg_color="transparent")
        controls.grid(
            row=2,
            column=0,
            sticky="e",
            padx=22,
            pady=(0, 20),
        )

        def copy_output():
            text = textbox.get("1.0", "end-1c")
            window.clipboard_clear()
            window.clipboard_append(text)
            self.status_label.configure(
                text=f"Status: {title.title()} copied to clipboard."
            )

        ctk.CTkButton(
            controls,
            text="COPY TO CLIPBOARD",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=copy_output,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            controls,
            text="CLOSE",
            fg_color="#374151",
            hover_color="#475569",
            command=window.destroy,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _update_statistics(self):
        now = datetime.now(timezone.utc)
        ages = []
        for story in self.stories:
            parsed = published_datetime(getattr(story, "published", ""))
            ages.append((now - parsed).days if parsed is not None else None)
        self.stat_labels["today"].configure(
            text=str(sum(age == 0 for age in ages))
        )
        self.stat_labels["recent"].configure(
            text=str(sum(age is not None and 1 <= age <= 3 for age in ages))
        )
        self.stat_labels["older"].configure(
            text=str(sum(age is None or age > 3 for age in ages))
        )
        self.stat_labels["review"].configure(
            text="1" if self.selected_story is not None else "0"
        )
        self.stat_labels["total"].configure(
            text=str(len(self.stories))
        )


def open_sport(master=None):
    """Open the Sport Intelligence workspace."""

    window = SportIntelligenceWindow(master)
    return window


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")

    app = ctk.CTk()
    app.withdraw()

    window = SportIntelligenceWindow(app)

    def close_application():
        window.destroy()
        app.destroy()

    window.protocol("WM_DELETE_WINDOW", close_application)
    app.mainloop()
