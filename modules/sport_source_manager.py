"""Dark-themed editor UI for managed Generic Website Sport sources."""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Any, Callable

import customtkinter as ctk

from newsdesk.sports.source_manager import SourceAnalysis, SourceManagerService
from newsdesk.sources.managed_websites import (
    MODULE_LABELS,
    manager_service,
    new_source_defaults,
    protected_sources,
)


LOGGER = logging.getLogger(__name__)

APP_BG = "#0f172a"
PANEL_BG = "#172033"
CARD_BG = "#1f2937"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
BORDER = "#334155"
RED = "#ed3b35"


class SportSourceManagerWindow(ctk.CTkToplevel):
    """Add, test, preview and persist Generic Website Sport sources."""

    FIELD_LABELS = (
        ("name", "Source name"),
        ("organisation", "Organisation"),
        ("listing_url", "Website or news-page URL"),
        ("sport", "Sport"),
        ("location", "Locality"),
        ("tags", "Tags (one per line or comma-separated)"),
        ("max_stories", "Maximum story count"),
    )
    ADVANCED_FIELDS = (
        ("article_link_selectors", "Article-link selectors"),
        ("card_selectors", "Card selectors"),
        ("include_url_patterns", "Include URL patterns"),
        ("exclude_url_patterns", "Exclude URL patterns"),
        ("exclude_title_patterns", "Exclude title patterns"),
        ("standalone_item_selectors", "Standalone item selectors"),
        ("listing_warmup_url", "Warm-up URL"),
        ("content_api_url", "Content API URL"),
        ("content_api_item_path", "Content API item path / record field"),
    )

    def __init__(
        self,
        master: Any,
        *,
        on_refresh: Callable[[], None] | None = None,
        service: SourceManagerService | None = None,
        module_profile: str = "sport",
        allow_custom_sources: bool = True,
    ) -> None:
        super().__init__(master)
        self.module_profile = str(module_profile or "sport").strip().casefold()
        self.module_label = MODULE_LABELS.get(
            self.module_profile, self.module_profile.title()
        )
        self.allow_custom_sources = bool(allow_custom_sources)
        self.title(f"{self.module_label} Source Manager")
        self.geometry("1280x820")
        self.minsize(1050, 680)
        self.configure(fg_color=APP_BG)
        self.transient(master)
        self.service = service or manager_service(self.module_profile)
        self.on_refresh = on_refresh
        self.current_id = ""
        self.dirty = False
        self.tested = False
        self.selected_preview_url = ""
        self.current_raw: dict[str, Any] = {}
        self.last_suggestions: dict[str, Any] = {}
        self.advanced_visible = False
        self.read_only = False
        self.variables: dict[str, ctk.Variable] = {}
        self.entries: dict[str, Any] = {}
        self.definitions: list[dict[str, Any]] = []
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self._reload_sources()
        self._new_source(confirm=False)

    def _build(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=5)
        self._build_left()
        self._build_right()

    def _build_left(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=PANEL_BG, border_width=1, border_color=BORDER)
        panel.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        panel.grid_rowconfigure(3, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            panel,
            text=f"{self.module_label.upper()} SOURCES",
            font=("Arial", 18, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8))
        ctk.CTkLabel(
            panel,
            text=(
                "Built-in sources are protected. Additions must pass Test Source."
                if self.allow_custom_sources
                else "This module uses a protected specialist collector."
            ),
            text_color=MUTED,
            anchor="w",
            wraplength=360,
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.search_var = ctk.StringVar(value="")
        self.search_var.trace_add("write", lambda *_: self._render_source_list())
        ctk.CTkEntry(
            panel,
            textvariable=self.search_var,
            placeholder_text="Search sources...",
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.source_list = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.source_list.grid(row=3, column=0, sticky="nsew", padx=8)
        ctk.CTkButton(
            panel,
            text="ADD NEW SOURCE",
            command=self._new_source,
            fg_color=RED,
            state="normal" if self.allow_custom_sources else "disabled",
        ).grid(row=4, column=0, sticky="ew", padx=12, pady=12)

    def _build_right(self) -> None:
        self.right = ctk.CTkScrollableFrame(self, fg_color=PANEL_BG, border_width=1, border_color=BORDER)
        self.right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        self.right.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.right,
            text="SOURCE DETAILS",
            font=("Arial", 18, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 10))
        self.form = ctk.CTkFrame(self.right, fg_color="transparent")
        self.form.grid(row=1, column=0, sticky="ew", padx=12)
        self.form.grid_columnconfigure(0, weight=1)
        row = 0
        for key, label in self.FIELD_LABELS:
            if key == "sport" and self.module_profile != "sport":
                label = "Category / topic"
            ctk.CTkLabel(
                self.form,
                text=label,
                text_color=MUTED,
                anchor="w",
            ).grid(row=row, column=0, sticky="ew", pady=(6, 2))
            variable = ctk.StringVar(value="")
            variable.trace_add("write", self._mark_dirty)
            entry = (
                ctk.CTkTextbox(self.form, height=58)
                if key == "tags"
                else ctk.CTkEntry(self.form, textvariable=variable)
            )
            if key == "tags":
                entry.bind("<KeyRelease>", self._textbox_changed)
            entry.grid(row=row + 1, column=0, sticky="ew")
            self.variables[key] = variable
            self.entries[key] = entry
            row += 2
        self.enabled_var = ctk.BooleanVar(value=True)
        self.enabled_var.trace_add("write", self._mark_dirty)
        self.enabled_checkbox = ctk.CTkCheckBox(
            self.form,
            text="Enabled",
            variable=self.enabled_var,
        )
        self.enabled_checkbox.grid(row=row, column=0, sticky="w", pady=10)

        ctk.CTkButton(
            self.right,
            text="ADVANCED SETTINGS",
            command=self._toggle_advanced,
            fg_color="#374151",
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(10, 4))
        self.advanced = ctk.CTkFrame(self.right, fg_color=CARD_BG)
        self.advanced.grid_columnconfigure(0, weight=1)
        for index, (key, label) in enumerate(self.ADVANCED_FIELDS):
            ctk.CTkLabel(
                self.advanced,
                text=label,
                text_color=MUTED,
                anchor="w",
            ).grid(
                row=index * 2,
                column=0,
                sticky="ew",
                padx=10,
                pady=(6, 2),
            )
            box = ctk.CTkTextbox(self.advanced, height=52)
            box.grid(row=index * 2 + 1, column=0, sticky="ew", padx=10)
            box.bind("<KeyRelease>", self._textbox_changed)
            self.entries[key] = box
        self.advanced.grid_remove()

        actions = ctk.CTkFrame(self.right, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=12, pady=10)
        self.test_button = ctk.CTkButton(actions, text="TEST SOURCE", command=self._test, fg_color=RED)
        self.test_button.pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="RESET", command=self._reset, fg_color="#374151").pack(side="left", padx=4)
        self.delete_button = ctk.CTkButton(actions, text="DELETE", command=self._delete, fg_color="#7f1d1d")
        self.delete_button.pack(side="right")

        self.status_label = ctk.CTkLabel(self.right, text="Not ready", font=("Arial", 14, "bold"), text_color=MUTED)
        self.status_label.grid(row=5, column=0, sticky="w", padx=16)
        self.results = ctk.CTkTextbox(self.right, height=140, wrap="word")
        self.results.grid(row=6, column=0, sticky="ew", padx=12, pady=8)
        self.apply_suggestions_button = ctk.CTkButton(
            self.right,
            text="APPLY REVIEWED SUGGESTIONS",
            command=self._apply_suggestions,
            state="disabled",
            fg_color="#374151",
        )
        self.apply_suggestions_button.grid(row=7, column=0, sticky="w", padx=12, pady=4)
        self.preview = ctk.CTkScrollableFrame(self.right, height=180, fg_color=CARD_BG)
        self.preview.grid(row=8, column=0, sticky="ew", padx=12, pady=6)
        self.deep_button = ctk.CTkButton(
            self.right,
            text="TEST SELECTED ARTICLE",
            command=self._deep_test,
            state="disabled",
            fg_color="#374151",
        )
        self.deep_button.grid(row=9, column=0, sticky="w", padx=12, pady=6)

        save = ctk.CTkFrame(self.right, fg_color="transparent")
        save.grid(row=10, column=0, sticky="e", padx=12, pady=(8, 16))
        self.save_button = ctk.CTkButton(
            save,
            text="SAVE",
            command=lambda: self._save(False),
            state="disabled",
            fg_color=RED,
        )
        self.save_button.pack(side="left", padx=4)
        self.save_refresh_button = ctk.CTkButton(
            save,
            text="SAVE AND REFRESH",
            command=lambda: self._save(True),
            state="disabled",
            fg_color=RED,
        )
        self.save_refresh_button.pack(side="left", padx=4)

    def _values(self) -> dict[str, Any]:
        values: dict[str, Any] = dict(self.current_raw)
        values["enabled"] = bool(self.enabled_var.get())
        for key, entry in self.entries.items():
            if isinstance(entry, ctk.CTkTextbox):
                value = entry.get("1.0", "end").strip()
            else:
                value = self.variables[key].get().strip()
            if key in {
                "tags",
                "article_link_selectors",
                "card_selectors",
                "include_url_patterns",
                "exclude_url_patterns",
                "exclude_title_patterns",
                "standalone_item_selectors",
            }:
                values[key] = [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]
            else:
                values[key] = value
        values["source_id"] = self.current_id
        values["module_profile"] = self.module_profile
        values.setdefault("max_age_days", new_source_defaults(self.module_profile)["max_age_days"])
        if not self.current_id:
            values["managed_by"] = "newsroom"
        return values

    def _set_values(self, values: dict[str, Any]) -> None:
        self.dirty = False
        self.current_raw = dict(values)
        for key, entry in self.entries.items():
            value = values.get(key, "")
            if isinstance(value, list):
                value = "\n".join(str(item) for item in value)
            if isinstance(entry, ctk.CTkTextbox):
                entry.delete("1.0", "end")
                entry.insert("1.0", str(value or ""))
            else:
                self.variables[key].set(str(value or ""))
        self.enabled_var.set(bool(values.get("enabled", True)))
        self.current_id = str(values.get("source_id") or "")
        self.tested = False
        self._set_save_state(False)
        self.dirty = False

    def _reload_sources(self) -> None:
        self.definitions = protected_sources(self.module_profile) + self.service.load_definitions()
        self._render_source_list()

    def _render_source_list(self) -> None:
        if not hasattr(self, "source_list"):
            return
        for widget in self.source_list.winfo_children():
            widget.destroy()
        query = self.search_var.get().strip().casefold()
        for source in self.definitions:
            protection = "  •  BUILT-IN" if source.get("protected") else ""
            label = f"{'●' if source.get('enabled', True) else '○'} {source.get('name', 'Untitled')}{protection}"
            if query and query not in label.casefold() and query not in str(source.get("organisation", "")).casefold():
                continue
            ctk.CTkButton(
                self.source_list,
                text=label,
                anchor="w",
                fg_color="#273449",
                command=lambda item=source: self._select(item),
            ).pack(fill="x", pady=2)

    def _select(self, source: dict[str, Any]) -> None:
        if not self._confirm_discard():
            return
        self._set_read_only(False)
        self._set_values(source)
        self._set_read_only(bool(source.get("protected")))
        self.delete_button.configure(
            state=(
                "normal"
                if source.get("managed_by") == "newsroom"
                else "disabled"
            )
        )

    def _new_source(self, confirm: bool = True) -> None:
        if confirm and not self._confirm_discard():
            return
        if not self.allow_custom_sources:
            if self.definitions:
                self._select(self.definitions[0])
            return
        self._set_read_only(False)
        self._set_values(new_source_defaults(self.module_profile))
        self.current_id = ""
        self.delete_button.configure(state="disabled")
        self.results.delete("1.0", "end")
        self._clear_preview()

    def _test(self) -> None:
        self.test_button.configure(state="disabled", text="TESTING...")
        self.update_idletasks()
        try:
            analysis = self.service.test_source(self._values(), current_id=self.current_id)
            self._show_analysis(analysis)
            self.tested = analysis.status != "Not ready"
            self._set_save_state(self.tested)
        except Exception as error:
            LOGGER.exception("Source Manager test failed")
            self._show_error(str(error))
        finally:
            self.test_button.configure(state="normal", text="TEST SOURCE")

    def _show_analysis(self, analysis: SourceAnalysis) -> None:
        self.status_label.configure(
            text=analysis.status,
            text_color=(
                "#22c55e"
                if analysis.status.startswith("Ready")
                else "#ef4444"
            ),
        )
        lines = [
            f"Resolved URL: {analysis.resolved_url or '(unavailable)'}",
            (
                f"HTTP: {analysis.http_status or '-'} • "
                f"redirects {analysis.redirect_count} • "
                f"{analysis.content_type or 'unknown'}"
            ),
            (
                f"Response: {analysis.response_seconds:.2f}s • "
                f"TLS validated: {'yes' if analysis.tls_validated else 'no'} • "
                f"type: {analysis.page_type}"
            ),
            (
                f"Links examined: {analysis.links_examined} • "
                f"candidates: {analysis.candidates_discovered} • "
                f"accepted/current: {analysis.current_stories} • "
                f"rejected: {analysis.candidates_rejected}"
            ),
        ]
        if analysis.error:
            lines.append("ERROR: " + analysis.error)
        if analysis.warnings:
            lines.append("WARNINGS:\n• " + "\n• ".join(analysis.warnings))
        if analysis.suggestions:
            lines.append(
                "SUGGESTIONS (review before applying):\n"
                + "\n".join(
                    f"{key}: {value}"
                    for key, value in analysis.suggestions.items()
                )
            )
        self.results.delete("1.0", "end")
        self.results.insert("1.0", "\n".join(lines))
        self._clear_preview()
        self.last_suggestions = dict(analysis.suggestions)
        self.apply_suggestions_button.configure(
            state="normal" if self.last_suggestions else "disabled"
        )
        for item in analysis.preview:
            label = (
                f"{item.title}\n{item.published or 'No date'} • "
                f"image {'yes' if item.image_available else 'no'} • "
                f"summary {'yes' if item.summary_available else 'no'} • "
                f"score {item.discovery_score}"
            )
            ctk.CTkButton(
                self.preview,
                text=label,
                anchor="w",
                height=52,
                fg_color="#273449",
                command=lambda url=item.url: self._select_preview(url),
            ).pack(fill="x", pady=2)

    def _apply_suggestions(self) -> None:
        if not self.last_suggestions:
            return
        listing_urls = self.last_suggestions.get("listing_urls") or []
        if listing_urls:
            self.variables["listing_url"].set(str(listing_urls[0]))
        for key, value in self.last_suggestions.items():
            if key == "listing_urls" or key not in self.entries:
                continue
            entry = self.entries[key]
            existing = (
                entry.get("1.0", "end").strip()
                if isinstance(entry, ctk.CTkTextbox)
                else self.variables[key].get().strip()
            )
            if existing:
                continue
            text = "\n".join(value) if isinstance(value, list) else str(value)
            if isinstance(entry, ctk.CTkTextbox):
                entry.insert("1.0", text)
            else:
                self.variables[key].set(text)
        self._mark_dirty()

    def _select_preview(self, url: str) -> None:
        self.selected_preview_url = url
        self.deep_button.configure(state="normal")

    def _deep_test(self) -> None:
        try:
            result = self.service.test_preview_article(self.selected_preview_url)
            messagebox.showinfo(
                "Article test",
                f"Extraction: {result['extraction_source']}\n"
                f"Words: {result['word_count']}\n"
                f"Summary: {'yes' if result['summary'] else 'no'}\n"
                f"Image: {'yes' if result['image_available'] else 'no'}\n"
                f"{result['error']}",
                parent=self,
            )
        except Exception as error:
            LOGGER.exception("Preview article test failed")
            messagebox.showerror("Article test failed", str(error), parent=self)

    def _save(self, refresh: bool) -> None:
        try:
            saved, backup = self.service.save_source(self._values(), current_id=self.current_id)
            self.current_id = str(saved["source_id"])
            self.dirty = False
            self._reload_sources()
            messagebox.showinfo("Source saved", f"Source saved.\nBackup: {backup.name}", parent=self)
            if refresh and self.on_refresh:
                self.on_refresh()
        except Exception as error:
            LOGGER.exception("Could not save Sport source")
            messagebox.showerror("Save failed", str(error), parent=self)

    def _delete(self) -> None:
        source = next((item for item in self.definitions if item.get("source_id") == self.current_id), None)
        if not source:
            return
        if not messagebox.askyesno(
            "Delete source",
            f"Delete {source.get('name')}?\n\n"
            "Cached stories and images will not be deleted.",
            parent=self,
        ):
            return
        try:
            self.service.delete_source(self.current_id)
            self._reload_sources()
            self._new_source(confirm=False)
        except Exception as error:
            LOGGER.exception("Could not delete Sport source")
            messagebox.showerror("Delete failed", str(error), parent=self)

    def _reset(self) -> None:
        if not self._confirm_discard():
            return
        source = next((item for item in self.definitions if item.get("source_id") == self.current_id), None)
        self._set_values(source or new_source_defaults(self.module_profile))

    def _set_read_only(self, value: bool) -> None:
        self.read_only = bool(value)
        state = "disabled" if self.read_only else "normal"
        for entry in self.entries.values():
            entry.configure(state=state)
        self.enabled_checkbox.configure(state=state)
        self.results.configure(state="normal")
        self.test_button.configure(state=state)
        self.apply_suggestions_button.configure(state="disabled")
        self.deep_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.save_refresh_button.configure(state="disabled")
        if self.read_only:
            status = self.current_raw.get("connection_status", "Configured")
            self.status_label.configure(text=f"BUILT-IN SOURCE — {status}", text_color="#22c55e")
            self.results.configure(state="normal")
            self.results.delete("1.0", "end")
            self.results.insert(
                "1.0",
                "This source is used by the module's protected specialist collector.\n"
                "It is shown here for visibility and cannot be edited or deleted.",
            )
            self.results.configure(state="disabled")

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.grid(row=3, column=0, sticky="ew", padx=12, pady=4)
        else:
            self.advanced.grid_remove()

    def _mark_dirty(self, *_args: Any) -> None:
        if not hasattr(self, "save_button"):
            return
        self.dirty = True
        self.tested = False
        self._set_save_state(False)

    def _textbox_changed(self, _event: Any) -> None:
        self._mark_dirty()

    def _set_save_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.save_button.configure(state=state)
        self.save_refresh_button.configure(state=state)

    def _confirm_discard(self) -> bool:
        return not self.dirty or messagebox.askyesno("Unsaved changes", "Discard unsaved changes?", parent=self)

    def _clear_preview(self) -> None:
        for widget in self.preview.winfo_children():
            widget.destroy()
        self.selected_preview_url = ""
        self.deep_button.configure(state="disabled")
        self.last_suggestions = {}
        self.apply_suggestions_button.configure(state="disabled")

    def _show_error(self, message: str) -> None:
        self.status_label.configure(text="Not ready", text_color="#ef4444")
        self.results.delete("1.0", "end")
        self.results.insert("1.0", message)
        self._set_save_state(False)

    def _close(self) -> None:
        if self._confirm_discard():
            self.destroy()


__all__ = ["SportSourceManagerWindow"]

# Shared name used by all current and future modules.
SourceManagerWindow = SportSourceManagerWindow
