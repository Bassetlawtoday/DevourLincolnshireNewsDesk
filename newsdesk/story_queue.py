"""
Reusable story queue component for Devour Lincolnshire NewsDesk modules.

The queue provides:

- a branded panel and heading
- live story count
- editorial filter menu
- scrollable story list
- empty-state messaging
- reusable story-card rendering
- selection callbacks
- filter callbacks

Example:

    queue = NewsDeskStoryQueue(
        parent,
        empty_title="No police stories loaded.",
        empty_message=(
            "Select “Refresh Police News” to collect the latest releases."
        ),
        on_filter_change=self.handle_filter_change,
        on_story_selected=self.handle_story_selected,
    )

    queue.grid(row=0, column=0, sticky="nsew")

    queue.set_stories(
        [
            {
                "id": "story-1",
                "title": "Police appeal following incident",
                "summary": "Officers are appealing for information.",
                "priority": "Urgent",
                "source": "Nottinghamshire Police",
            }
        ]
    )
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Optional

import customtkinter as ctk

from newsdesk.theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    CARD_BG,
    HEADER_BG,
    PANEL_BG,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    CARD_CORNER_RADIUS,
    CARD_HORIZONTAL_PADDING,
    CARD_VERTICAL_PADDING,
    CONTROL_HEIGHT,
    PANEL_CORNER_RADIUS,
    STANDARD_BORDER_WIDTH,
)


class NewsDeskStoryQueue(ctk.CTkFrame):
    """
    Shared editorial story queue.

    Each story may be supplied as a mapping containing any of these fields:

        id
        title
        summary
        priority
        source
        published
        status

    Only ``title`` is required. Missing optional fields are handled safely.
    """

    DEFAULT_FILTERS = (
        "All stories",
        "Immediate",
        "Urgent",
        "Routine",
        "Editor review",
    )

    PRIORITY_COLOURS = {
        "immediate": "#ef4444",
        "urgent": "#f97316",
        "routine": "#eab308",
        "editor review": ACCENT,
        "review": ACCENT,
    }

    _RENDER_BATCH_SIZE = 5
    _RENDER_BATCH_DELAY_MS = 50

    def __init__(
        self,
        master,
        *,
        title: str = "STORY QUEUE",
        filters: Iterable[str] = DEFAULT_FILTERS,
        empty_title: str = "No stories loaded.",
        empty_message: str = "Refresh this module to collect the latest stories.",
        on_filter_change: Optional[Callable[[str], None]] = None,
        on_story_selected: Optional[Callable[[Mapping[str, Any]], None]] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=HEADER_BG,
            corner_radius=PANEL_CORNER_RADIUS,
            border_width=STANDARD_BORDER_WIDTH,
            border_color=BORDER,
            **kwargs,
        )

        self.panel_title = title
        self.filters = tuple(filters)
        self.empty_title = empty_title
        self.empty_message = empty_message
        self.on_filter_change = on_filter_change
        self.on_story_selected = on_story_selected

        if not self.filters:
            raise ValueError("NewsDeskStoryQueue requires at least one filter.")

        self._stories: list[dict[str, Any]] = []
        self._story_buttons: list[ctk.CTkBaseClass] = []
        self._selected_story_id: Any = None
        self._render_after_id: Optional[str] = None
        self._render_generation = 0
        self._render_signature: Optional[tuple[tuple[Any, ...], ...]] = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_heading()
        self._build_filter()
        self._build_story_list()
        self._show_empty_state()
        self.bind("<Destroy>", self._handle_destroy, add="+")

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_heading(self) -> None:
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=18,
            pady=(17, 10),
        )

        ctk.CTkLabel(
            heading,
            text=self.panel_title.upper(),
            font=("Arial", 16, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self.queue_count_label = ctk.CTkLabel(
            heading,
            text="0 STORIES",
            font=("Arial", 11, "bold"),
            text_color=TEXT_MUTED,
        )
        self.queue_count_label.pack(side="right")

    def _build_filter(self) -> None:
        self.filter_menu = ctk.CTkOptionMenu(
            self,
            values=self.filters,
            height=CONTROL_HEIGHT,
            fg_color=CARD_BG,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=CARD_BG,
            dropdown_hover_color="#475569",
            dropdown_text_color=TEXT_PRIMARY,
            font=("Arial", 12),
            dropdown_font=("Arial", 12),
            command=self._handle_filter_change,
        )
        self.filter_menu.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=18,
            pady=(0, 12),
        )
        self.filter_menu.set(self.filters[0])

    def _build_story_list(self) -> None:
        self.story_list = ctk.CTkScrollableFrame(
            self,
            fg_color=PANEL_BG,
            corner_radius=12,
        )
        self.story_list.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(0, 12),
        )
        self.story_list.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Empty state
    # ------------------------------------------------------------------

    def _show_empty_state(self) -> None:
        self._clear_story_widgets()

        self.empty_state = ctk.CTkFrame(
            self.story_list,
            fg_color="transparent",
        )
        self.empty_state.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=25,
            pady=80,
        )

        ctk.CTkLabel(
            self.empty_state,
            text=self.empty_title,
            font=("Arial", 14, "bold"),
            text_color=TEXT_PRIMARY,
            justify="center",
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            self.empty_state,
            text=self.empty_message,
            font=("Arial", 13),
            text_color=TEXT_MUTED,
            justify="center",
            wraplength=280,
        ).pack()

    def set_empty_state(
        self,
        *,
        title: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        """Update the empty-state copy."""

        if title is not None:
            self.empty_title = title

        if message is not None:
            self.empty_message = message

        if not self._stories:
            self._show_empty_state()

    # ------------------------------------------------------------------
    # Story management
    # ------------------------------------------------------------------

    def set_stories(
        self,
        stories: Iterable[Mapping[str, Any]],
    ) -> None:
        """Replace all stories currently displayed in the queue."""

        normalised_stories = [
            self._normalise_story(story, index)
            for index, story in enumerate(stories)
        ]
        signature = self._story_signature(normalised_stories)
        self._stories = normalised_stories
        self._selected_story_id = None
        if signature == self._render_signature:
            self._update_count()
            return
        self._render_signature = signature
        self._render_stories()

    def append_story(self, story: Mapping[str, Any]) -> None:
        """Append one story to the queue."""

        normalised = self._normalise_story(story, len(self._stories))
        self._stories.append(normalised)
        self._render_signature = self._story_signature(self._stories)
        self._render_stories()

    def clear_stories(self) -> None:
        """Remove all stories and restore the empty state."""

        self._stories.clear()
        self._selected_story_id = None
        self._render_signature = self._story_signature(self._stories)
        self._update_count()
        self._show_empty_state()

    def get_stories(self) -> tuple[dict[str, Any], ...]:
        """Return a safe snapshot of the queue contents."""

        return tuple(dict(story) for story in self._stories)

    def get_selected_story(self) -> Optional[dict[str, Any]]:
        """Return the selected story, or ``None``."""

        for story in self._stories:
            if story["id"] == self._selected_story_id:
                return dict(story)

        return None

    def select_story(self, story_id: Any) -> bool:
        """
        Select a story programmatically.

        Returns ``True`` when the story exists, otherwise ``False``.
        """

        for story in self._stories:
            if story["id"] == story_id:
                self._handle_story_selected(story)
                return True

        return False

    @staticmethod
    def _normalise_story(
        story: Mapping[str, Any],
        index: int,
    ) -> dict[str, Any]:
        """Validate and normalise one story mapping."""

        if not isinstance(story, Mapping):
            raise TypeError("Each story must be a mapping.")

        title = str(story.get("title", "")).strip()

        if not title:
            raise ValueError("Each story requires a non-empty title.")

        normalised = dict(story)
        normalised["id"] = story.get("id", f"story-{index + 1}")
        normalised["title"] = title
        normalised["summary"] = str(story.get("summary", "")).strip()
        normalised["priority"] = str(story.get("priority", "")).strip()
        normalised["source"] = str(story.get("source", "")).strip()
        normalised["published"] = str(story.get("published", "")).strip()
        normalised["status"] = str(story.get("status", "")).strip()

        return normalised

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_stories(self) -> None:
        self._cancel_pending_render()
        self._clear_story_widgets()
        self._update_count()

        if not self._stories:
            self._show_empty_state()
            return

        if len(self._stories) <= self._RENDER_BATCH_SIZE:
            self._render_story_batch(self._render_generation, 0)
            return

        generation = self._render_generation
        self._render_after_id = self.after_idle(
            lambda: self._render_story_batch(generation, 0)
        )

    def _render_story_batch(self, generation: int, start: int) -> None:
        """Render one bounded batch and yield back to Tk between batches."""

        self._render_after_id = None
        if generation != self._render_generation or not self.winfo_exists():
            return

        stop = min(start + self._RENDER_BATCH_SIZE, len(self._stories))
        for row in range(start, stop):
            story = self._stories[row]
            card = self._create_story_card(story)
            card.grid(
                row=row,
                column=0,
                sticky="ew",
                padx=4,
                pady=(4, 8),
            )
            self._story_buttons.append(card)

        if stop < len(self._stories):
            self._render_after_id = self.after(
                self._RENDER_BATCH_DELAY_MS,
                lambda: self._render_story_batch(generation, stop),
            )

    @staticmethod
    def _story_signature(
        stories: Iterable[Mapping[str, Any]],
    ) -> tuple[tuple[tuple[str, str], ...], ...]:
        """Return the display-relevant identity of a queue payload."""

        return tuple(
            tuple(
                (str(key), repr(value))
                for key, value in sorted(story.items(), key=lambda item: str(item[0]))
            )
            for story in stories
        )

    def _cancel_pending_render(self) -> None:
        """Invalidate and cancel any queued rendering work."""

        self._render_generation += 1
        if self._render_after_id is None:
            return
        try:
            self.after_cancel(self._render_after_id)
        except Exception:
            pass
        self._render_after_id = None

    def _handle_destroy(self, event) -> None:
        if event.widget is self:
            self._cancel_pending_render()

    def _create_story_card(
        self,
        story: Mapping[str, Any],
    ) -> ctk.CTkFrame:
        """
        Create one left-aligned clickable story card.

        A frame with separate labels is used instead of a CTkButton so long
        titles, dates and scores remain readable and align consistently from
        the left edge.
        """

        priority = str(story.get("priority", "")).strip()
        source = str(story.get("source", "")).strip()
        published = str(story.get("published", "")).strip()
        summary = str(story.get("summary", "")).strip()
        is_selected = story.get("id") == self._selected_story_id

        card = ctk.CTkFrame(
            self.story_list,
            fg_color="#374151" if is_selected else CARD_BG,
            corner_radius=CARD_CORNER_RADIUS,
            border_width=STANDARD_BORDER_WIDTH,
            border_color=ACCENT if is_selected else self._priority_colour(priority),
            cursor="hand2",
        )
        card.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            card,
            text=str(story["title"]),
            anchor="w",
            justify="left",
            wraplength=330,
            font=("Arial", 12, "bold"),
            text_color=TEXT_PRIMARY,
        )
        title_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=CARD_HORIZONTAL_PADDING,
            pady=(CARD_VERTICAL_PADDING, 5),
        )

        primary_metadata = "  •  ".join(
            part for part in (priority, source) if part
        )
        if primary_metadata:
            metadata_label = ctk.CTkLabel(
                card,
                text=primary_metadata,
                anchor="w",
                justify="left",
                wraplength=330,
                font=("Arial", 10, "bold"),
                text_color=TEXT_SECONDARY,
            )
            metadata_label.grid(
                row=1,
                column=0,
                sticky="ew",
                padx=CARD_HORIZONTAL_PADDING,
                pady=(0, 3),
            )
        else:
            metadata_label = None

        if published:
            published_label = ctk.CTkLabel(
                card,
                text=published,
                anchor="w",
                justify="left",
                wraplength=330,
                font=("Arial", 10),
                text_color=TEXT_MUTED,
            )
            published_label.grid(
                row=2,
                column=0,
                sticky="ew",
                padx=CARD_HORIZONTAL_PADDING,
                pady=(0, 4),
            )
        else:
            published_label = None

        if summary:
            shortened = (
                summary
                if len(summary) <= 190
                else f"{summary[:187].rstrip()}..."
            )
            summary_label = ctk.CTkLabel(
                card,
                text=shortened,
                anchor="w",
                justify="left",
                wraplength=330,
                font=("Arial", 10),
                text_color=TEXT_MUTED,
            )
            summary_label.grid(
                row=3,
                column=0,
                sticky="ew",
                padx=CARD_HORIZONTAL_PADDING,
                pady=(0, CARD_VERTICAL_PADDING),
            )
        else:
            summary_label = None
            bottom_row = 2 if published else (1 if primary_metadata else 0)
            card.grid_slaves(row=bottom_row, column=0)[0].grid_configure(
                pady=(0, 11)
            )

        selected = dict(story)
        clickable_widgets = [
            card,
            title_label,
            metadata_label,
            published_label,
            summary_label,
        ]

        for widget in clickable_widgets:
            if widget is None:
                continue
            widget.bind(
                "<Button-1>",
                lambda _event, item=selected: self._handle_story_selected(item),
            )
            widget.bind(
                "<Enter>",
                lambda _event, panel=card: panel.configure(
                    fg_color="#374151"
                ),
            )
            widget.bind(
                "<Leave>",
                lambda _event, panel=card: panel.configure(
                    fg_color=(
                        "#374151"
                        if selected.get("id") == self._selected_story_id
                        else CARD_BG
                    )
                ),
            )

        return card

    def _clear_story_widgets(self) -> None:
        """Destroy all widgets currently inside the story list."""

        for widget in self.story_list.winfo_children():
            widget.destroy()

        self._story_buttons.clear()

    def _update_count(self) -> None:
        count = len(self._stories)
        noun = "STORY" if count == 1 else "STORIES"
        self.queue_count_label.configure(text=f"{count} {noun}")

    @classmethod
    def _priority_colour(cls, priority: str) -> str:
        return cls.PRIORITY_COLOURS.get(
            priority.strip().lower(),
            BORDER,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _handle_filter_change(self, selected_filter: str) -> None:
        if self.on_filter_change is not None:
            self.on_filter_change(selected_filter)

    def _handle_story_selected(
        self,
        story: Mapping[str, Any],
    ) -> None:
        self._selected_story_id = story.get("id")
        self._apply_selection_style()

        if self.on_story_selected is not None:
            self.on_story_selected(dict(story))

    def _apply_selection_style(self) -> None:
        """Update card colours without changing card geometry."""
        for story, card in zip(self._stories, self._story_buttons):
            selected = story.get("id") == self._selected_story_id
            card.configure(
                fg_color="#374151" if selected else CARD_BG,
                border_color=ACCENT if selected else self._priority_colour(
                    str(story.get("priority", ""))
                ),
            )

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------

    def get_filter(self) -> str:
        """Return the currently selected filter."""

        return self.filter_menu.get()

    def set_filter(self, value: str, *, notify: bool = False) -> None:
        """Set the active filter."""

        if value not in self.filters:
            raise ValueError(
                f"Unknown filter {value!r}. "
                f"Available filters: {', '.join(self.filters)}"
            )

        self.filter_menu.set(value)

        if notify:
            self._handle_filter_change(value)

    def set_filter_enabled(self, enabled: bool) -> None:
        """Enable or disable the filter menu."""

        state = "normal" if enabled else "disabled"
        self.filter_menu.configure(state=state)
