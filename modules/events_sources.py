from __future__ import annotations

import customtkinter as ctk

from eventsdesk.source_catalog import SourceCatalog
from eventsdesk.source_scope import (
    COUNTIES, counties_for_area, eligible_sources,
    load_disabled_source_ids, save_disabled_source_ids,
)
from newsdesk.theme import (
    ACTION_BLUE, ACTION_BLUE_HOVER, APP_BG, CARD_BG, HEADER_BG,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


class EventSourceManager(ctk.CTkToplevel):
    """EventsDesk-only feed switches for the Greater Lincolnshire footprint."""

    def __init__(self, master, data_dir, on_saved=None):
        super().__init__(master)
        self.data_dir = data_dir
        self.on_saved = on_saved
        self.catalog = SourceCatalog.load_default()
        self.sources = eligible_sources(self.catalog)
        self.disabled = load_disabled_source_ids(data_dir)
        self.vars = {}
        self.title("EventsDesk Sources - NewsDesk Pro")
        self.geometry("920x760")
        self.minsize(760, 620)
        self.configure(fg_color=APP_BG)
        self.transient(master)
        self._build()
        self.grab_set()

    def _build(self):
        top = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(
            top, text="EVENTSDESK SOURCES", font=("Arial", 23, "bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(
            top,
            text="Greater Lincolnshire feeds are available here, including North and North East Lincolnshire. Cinema-only sources and film-classified events are excluded. Untick any feed you do not want refreshed.",
            text_color=TEXT_SECONDARY, wraplength=820, justify="left"
        ).pack(anchor="w", padx=24, pady=(0, 16))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkButton(actions, text="ENABLE ALL", width=120, command=lambda:self._set_all(True),
                      fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER).pack(side="left", padx=(0,8))
        ctk.CTkButton(actions, text="DISABLE ALL", width=120, command=lambda:self._set_all(False),
                      fg_color="#374151", hover_color="#475569").pack(side="left")
        self.count_label = ctk.CTkLabel(actions, text="", text_color=TEXT_MUTED)
        self.count_label.pack(side="right")

        scroll = ctk.CTkScrollableFrame(self, fg_color=CARD_BG)
        scroll.pack(fill="both", expand=True, padx=20, pady=10)
        current_county = None
        for source in sorted(self.sources, key=lambda s: (counties_for_area(s.area)[0], s.name.casefold())):
            county = counties_for_area(source.area)[0]
            if county != current_county:
                current_county = county
                ctk.CTkLabel(scroll, text=county.upper(), font=("Arial",13,"bold"),
                             text_color=TEXT_PRIMARY).pack(anchor="w", padx=10, pady=(14,4))
            var = ctk.BooleanVar(value=source.id not in self.disabled)
            self.vars[source.id] = var
            cb = ctk.CTkCheckBox(
                scroll, text=f"{source.name}   —   {source.area}",
                variable=var, text_color=TEXT_SECONDARY, command=self._update_count
            )
            cb.pack(anchor="w", padx=18, pady=4)
        self._update_count()

        bottom = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0)
        bottom.pack(fill="x")
        ctk.CTkButton(bottom, text="SAVE", width=130, fg_color=ACTION_BLUE,
                      hover_color=ACTION_BLUE_HOVER, command=self._save).pack(side="right", padx=(8,20), pady=14)
        ctk.CTkButton(bottom, text="CANCEL", width=110, fg_color="#374151",
                      hover_color="#475569", command=self.destroy).pack(side="right", pady=14)

    def _set_all(self, value):
        for var in self.vars.values():
            var.set(value)
        self._update_count()

    def _update_count(self):
        enabled = sum(1 for var in self.vars.values() if var.get())
        self.count_label.configure(text=f"{enabled} of {len(self.vars)} feeds enabled")

    def _save(self):
        disabled = {source_id for source_id, var in self.vars.items() if not var.get()}
        save_disabled_source_ids(self.data_dir, disabled)
        if self.on_saved:
            self.on_saved()
        self.destroy()
