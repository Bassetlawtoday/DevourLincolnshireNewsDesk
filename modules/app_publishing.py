"""Devour News App Publishing: local editorial review screen.

No public publishing occurs until a cloud endpoint has been agreed and built.
"""
from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox

from newsdesk.app_publishing.store import AppArticleStore
from newsdesk.app_publishing.areas import available_areas

BG = "#0f172a"
PANEL = "#1f2937"
TEXT = "#f8fafc"
MUTED = "#cbd5e1"
BLUE = "#2563eb"


class AppPublishingWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Devour News - App Publishing")
        self.geometry("1250x820")
        self.configure(fg_color=BG)
        self.store = AppArticleStore()
        self.current_id = None
        self.search_var = ctk.StringVar()
        self.areas_var = ctk.StringVar()
        self.category_var = ctk.StringVar()
        self.notify_var = ctk.BooleanVar(value=False)
        self._build()
        self._refresh()

    def _build(self):
        ctk.CTkLabel(self, text="DEVOUR NEWS  |  APP PUBLISHING", font=("Arial", 24, "bold"), text_color=TEXT).pack(anchor="w", padx=22, pady=(20, 4))
        ctk.CTkLabel(self, text="Editorial drafts only - cloud publishing is not connected", text_color=MUTED).pack(anchor="w", padx=22)
        layout = ctk.CTkFrame(self, fg_color="transparent")
        layout.pack(fill="both", expand=True, padx=18, pady=15)
        layout.grid_columnconfigure(0, weight=1)
        layout.grid_columnconfigure(1, weight=3)
        layout.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(layout, fg_color=PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkEntry(left, textvariable=self.search_var, placeholder_text="Search incoming articles").pack(fill="x", padx=10, pady=10)
        self.search_var.trace_add("write", lambda *_: self._refresh())
        self.list_box = ctk.CTkScrollableFrame(left, fg_color=PANEL)
        self.list_box.pack(fill="both", expand=True, padx=8, pady=8)
        right = ctk.CTkFrame(layout, fg_color=PANEL)
        right.grid(row=0, column=1, sticky="nsew")
        form = ctk.CTkScrollableFrame(right, fg_color=PANEL)
        form.pack(fill="both", expand=True, padx=14, pady=10)
        self.title_entry = self._entry(form, "Headline")
        ctk.CTkLabel(form, text="Article (target approximately 500 words)", text_color=TEXT).pack(anchor="w", pady=(10, 3))
        self.body_box = ctk.CTkTextbox(form, height=240, font=("Arial", 15))
        self.body_box.pack(fill="x")
        self.body_box.bind("<KeyRelease>", lambda _event: self._count_words())
        self.counter = ctk.CTkLabel(form, text="0 words", text_color=MUTED)
        self.counter.pack(anchor="e")
        ctk.CTkLabel(form, text="Original source article (read only)", text_color=TEXT).pack(anchor="w", pady=(8, 3))
        self.original_box = ctk.CTkTextbox(form, height=130)
        self.original_box.pack(fill="x")
        self.original_box.configure(state="disabled")
        self.source_label = ctk.CTkLabel(form, text="Source: -", text_color=MUTED, wraplength=650, justify="left")
        self.source_label.pack(anchor="w", pady=(10, 0))
        self.image_entry = self._entry(form, "Image URL")
        self.caption_entry = self._entry(form, "Image caption")
        self.credit_entry = self._entry(form, "Image credit")
        ctk.CTkLabel(form, text="County: Lincolnshire", text_color=TEXT).pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(form, text="Areas (comma-separated; leave blank for all Lincolnshire)", text_color=TEXT).pack(anchor="w")
        self.areas_menu = ctk.CTkComboBox(form, values=["All Lincolnshire", *available_areas()], state="readonly", command=self._add_area)
        self.areas_menu.pack(fill="x", pady=(3, 5))
        self.areas_menu.set("All Lincolnshire")
        ctk.CTkLabel(form, text="Selected areas (comma-separated; blank means all Lincolnshire)", text_color=MUTED).pack(anchor="w")
        ctk.CTkEntry(form, textvariable=self.areas_var).pack(fill="x", pady=(3, 5))
        ctk.CTkLabel(form, text="Category", text_color=TEXT).pack(anchor="w")
        ctk.CTkEntry(form, textvariable=self.category_var).pack(fill="x", pady=(3, 5))
        ctk.CTkCheckBox(form, text="Mark for reader notification (not sent until cloud integration)", variable=self.notify_var).pack(anchor="w", pady=8)
        controls = ctk.CTkFrame(right, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=12)
        ctk.CTkButton(controls, text="SAVE DRAFT", command=self._save, fg_color=BLUE).pack(side="left", padx=(0, 8))
        ctk.CTkButton(controls, text="PUBLISH (NOT CONNECTED)", state="disabled").pack(side="left", padx=(0, 8))
        ctk.CTkButton(controls, text="WITHDRAW (NOT CONNECTED)", state="disabled").pack(side="left")
        self.status_label = ctk.CTkLabel(right, text="Select an article to edit", text_color=MUTED)
        self.status_label.pack(anchor="w", padx=14, pady=(0, 10))

    @staticmethod
    def _entry(parent, label):
        ctk.CTkLabel(parent, text=label, text_color=TEXT).pack(anchor="w", pady=(8, 3))
        entry = ctk.CTkEntry(parent)
        entry.pack(fill="x")
        return entry

    def _refresh(self):
        for child in self.list_box.winfo_children():
            child.destroy()
        try:
            articles = self.store.load()
        except (OSError, ValueError) as error:
            messagebox.showerror("App Publishing", str(error), parent=self)
            return
        query = self.search_var.get().strip().casefold()
        for article in sorted(articles, key=lambda item: item.updated_at, reverse=True):
            if query and query not in (article.title + " " + article.body).casefold():
                continue
            ctk.CTkButton(
                self.list_box, text=(article.title or "Untitled")[:70],
                anchor="w", fg_color="#334155", height=44,
                command=lambda item=article: self._open_article(item),
            ).pack(fill="x", pady=3)

    def _add_area(self, value):
        if value == "All Lincolnshire":
            self.areas_var.set("")
        else:
            selected = [x.strip() for x in self.areas_var.get().split(",") if x.strip()]
            if value not in selected:
                selected.append(value)
            self.areas_var.set(", ".join(selected))

    def _open_article(self, article):
        self.current_id = article.article_id
        self._set_entry(self.title_entry, article.title)
        self.body_box.delete("1.0", "end")
        self.body_box.insert("1.0", article.body)
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.insert("1.0", article.original_body)
        self.original_box.configure(state="disabled")
        self.source_label.configure(text=f"Source: {article.source}\n{article.source_url}")
        self._set_entry(self.image_entry, article.image_url)
        self._set_entry(self.caption_entry, article.image_caption)
        self._set_entry(self.credit_entry, article.image_credit)
        self.areas_var.set(", ".join(article.areas))
        self.category_var.set(article.category)
        self.notify_var.set(article.notify_readers)
        self._count_words()
        self.status_label.configure(text=f"Editing local draft: {article.title}")

    @staticmethod
    def _set_entry(entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def _count_words(self):
        words = len(self.body_box.get("1.0", "end-1c").split())
        self.counter.configure(text=f"{words} words (approximately 500 target)")

    def _save(self):
        if not self.current_id:
            messagebox.showinfo("App Publishing", "Select an article first.", parent=self)
            return
        articles = self.store.load()
        article = next((item for item in articles if item.article_id == self.current_id), None)
        if article is None:
            messagebox.showerror("App Publishing", "The selected draft no longer exists.", parent=self)
            return
        article.title = self.title_entry.get().strip()
        article.body = self.body_box.get("1.0", "end-1c").strip()
        article.image_url = self.image_entry.get().strip()
        article.image_caption = self.caption_entry.get().strip()
        article.image_credit = self.credit_entry.get().strip()
        article.areas = list(dict.fromkeys(x.strip() for x in self.areas_var.get().split(",") if x.strip()))
        article.category = self.category_var.get().strip()
        article.notify_readers = self.notify_var.get()
        self.store.upsert(article)
        self.status_label.configure(text="Local draft saved. Not published.")
        self._refresh()


def open_app_publishing(master):
    return AppPublishingWindow(master)
