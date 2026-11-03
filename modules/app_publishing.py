"""Devour News App Publishing: local editorial review screen.

No public publishing occurs until a cloud endpoint has been agreed and built.
"""
from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox
from PIL import Image
from io import BytesIO
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse
from urllib.request import urlopen
import queue
import webbrowser

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
        self._loaded_snapshot = None
        self._preview_token = 0
        self._preview_image = None
        self._preview_results = queue.Queue()
        self.search_var = ctk.StringVar()
        self.areas_var = ctk.StringVar()
        self.category_var = ctk.StringVar()
        self.notify_var = ctk.BooleanVar(value=False)
        self.notification_type_var = ctk.StringVar(value='Breaking news')
        self.notification_message_var = ctk.StringVar()
        self._build()
        self._refresh()
        self.after(150, self._poll_preview)

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
        self.body_box = ctk.CTkTextbox(form, height=240, font=("Arial", 15), wrap="word")
        self.body_box.pack(fill="x")
        self.body_box.bind("<KeyRelease>", lambda _event: self._count_words())
        self.counter = ctk.CTkLabel(form, text="0 words", text_color=MUTED)
        self.counter.pack(anchor="e")
        ctk.CTkLabel(form, text="Original source article (read only)", text_color=TEXT).pack(anchor="w", pady=(8, 3))
        self.original_box = ctk.CTkTextbox(form, height=130, wrap="word")
        self.original_box.pack(fill="x")
        self.original_box.configure(state="disabled")
        self.source_label = ctk.CTkLabel(form, text="Source: -", text_color=MUTED, wraplength=650, justify="left")
        self.source_label.pack(anchor="w", pady=(10, 0))
        self.source_link = ctk.CTkButton(form, text="OPEN ORIGINAL SOURCE", command=self._open_source, width=190, anchor="w")
        self.source_link.pack(anchor="w", pady=(3, 8))
        self.source_url = ""
        self.image_entry = self._entry(form, "Image URL")
        self.image_preview = ctk.CTkLabel(form, text="No image selected", text_color=TEXT, height=110)
        self.image_preview.pack(anchor="w", pady=(8, 3))
        ctk.CTkButton(form, text="REFRESH IMAGE PREVIEW", width=190, command=self._load_preview).pack(anchor="w", pady=(0, 8))
        self.caption_entry = self._entry(form, "Image caption")
        self.credit_entry = self._entry(form, "Image credit")
        ctk.CTkLabel(form, text="County: Lincolnshire", text_color=TEXT).pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(form, text="Add a town or area (choose All Lincolnshire to clear)", text_color=TEXT).pack(anchor="w")
        self.areas_menu = ctk.CTkComboBox(form, values=["All Lincolnshire", *available_areas()], state="readonly", command=self._add_area)
        self.areas_menu.pack(fill="x", pady=(3, 5))
        self.areas_menu.set("All Lincolnshire")
        ctk.CTkLabel(form, text="Selected areas (editable; blank means all Lincolnshire)", text_color=MUTED).pack(anchor="w")
        ctk.CTkEntry(form, textvariable=self.areas_var).pack(fill="x", pady=(3, 5))
        ctk.CTkLabel(form, text="Category", text_color=TEXT).pack(anchor="w")
        ctk.CTkEntry(form, textvariable=self.category_var).pack(fill="x", pady=(3, 5))
        ctk.CTkCheckBox(form, text="Mark for reader notification (not sent until cloud integration)", variable=self.notify_var, text_color=TEXT, fg_color=BLUE, hover_color=BLUE, border_color=MUTED).pack(anchor="w", pady=8)
        ctk.CTkLabel(form, text="Notification type (editorial choice; not sent)", text_color=TEXT).pack(anchor="w")
        ctk.CTkOptionMenu(form, variable=self.notification_type_var, values=["Breaking news", "Local news", "Important update"]).pack(anchor="w", pady=(3, 8))
        self.notification_message_entry = self._entry(form, "Notification message (optional)")
        ctk.CTkButton(form, text="PREVIEW READER NOTIFICATION", command=self._preview_notification).pack(anchor="w", pady=(4, 10))
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

    def _editor_values(self):
        return (
            self.title_entry.get(),
            self.body_box.get("1.0", "end-1c").strip(),
            self.image_entry.get(),
            self.caption_entry.get(),
            self.credit_entry.get(),
            tuple(x.strip() for x in self.areas_var.get().split(",") if x.strip()),
            self.category_var.get(),
            self.notify_var.get(),
            self.notification_type_var.get(),
            self.notification_message_entry.get(),
        )

    def _open_source(self):
        parsed = urlparse(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            messagebox.showinfo("App Publishing", "No valid source link is available.", parent=self)
            return
        webbrowser.open(self.source_url)

    def _preview_notification(self):
        title = self.title_entry.get().strip() or "Untitled article"
        message = self.notification_message_entry.get().strip() or title
        messagebox.showinfo(
            "Reader notification preview",
            f"Type: {self.notification_type_var.get()}\n\n"
            f"Title: {title}\n\nMessage: {message}\n\n"
            "Preview only. No notification has been sent.",
            parent=self,
        )

    def _poll_preview(self):
        try:
            while True:
                token, result, error = self._preview_results.get_nowait()
                if token != self._preview_token:
                    continue
                if error:
                    self.image_preview.configure(image=None, text="Preview unavailable: " + error[:110])
                else:
                    self._preview_image = ctk.CTkImage(light_image=result, dark_image=result, size=result.size)
                    self.image_preview.configure(image=self._preview_image, text="")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._poll_preview)

    def _load_preview(self):
        self._preview_token += 1
        token = self._preview_token
        self._preview_image = None
        self.image_preview.configure(image=None, text="Loading image preview...")
        url = self.image_entry.get().strip()
        parsed = urlparse(url)
        if "placeholder" in parsed.path.casefold():
            self.image_preview.configure(text="Source supplied a placeholder, not a story photograph")
            return
        if parsed.scheme != "https" or not parsed.netloc:
            self.image_preview.configure(text="No HTTPS image URL available")
            return

        def fetch():
            try:
                with urlopen(url, timeout=6) as response:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if not content_type.startswith("image/"):
                        raise ValueError("The source did not return an image")
                    data = response.read(5_000_001)
                    if len(data) > 5_000_000:
                        raise ValueError("Image exceeds the 5 MB preview limit")
                image = Image.open(BytesIO(data))
                image.thumbnail((500, 250))
                image.load()
                self._preview_results.put((token, image.copy(), None))
            except Exception as exc:
                self._preview_results.put((token, None, str(exc)))

        Thread(target=fetch, daemon=True).start()

    def _open_article(self, article):
        if self.current_id and article.article_id != self.current_id and self._loaded_snapshot is not None:
            if self._editor_values() != self._loaded_snapshot:
                choice = messagebox.askyesnocancel(
                    "Unsaved changes",
                    "Save your changes before opening another article?\n\n"
                    "Yes: save changes. No: discard changes. Cancel: stay here.",
                    parent=self,
                )
                if choice is None:
                    return
                if choice and not self._save():
                    return
        self.current_id = article.article_id
        self._set_entry(self.title_entry, article.title)
        self.body_box.delete("1.0", "end")
        self.body_box.insert("1.0", article.body)
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.insert("1.0", article.original_body)
        self.original_box.configure(state="disabled")
        self.source_label.configure(text=f"Source: {article.source}")
        self.source_url = article.source_url
        self.source_link.configure(state="normal" if urlparse(self.source_url).scheme in {"http", "https"} else "disabled")
        self._set_entry(self.image_entry, article.image_url)
        self._set_entry(self.caption_entry, article.image_caption)
        self._set_entry(self.credit_entry, article.image_credit)
        self.areas_var.set(", ".join(article.areas))
        self.category_var.set(article.category)
        self.notify_var.set(article.notify_readers)
        self.notification_type_var.set(article.notification_type)
        self._set_entry(self.notification_message_entry, article.notification_message)
        self._count_words()
        self._loaded_snapshot = self._editor_values()
        self._load_preview()
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
            return False
        articles = self.store.load()
        article = next((item for item in articles if item.article_id == self.current_id), None)
        if article is None:
            messagebox.showerror("App Publishing", "The selected draft no longer exists.", parent=self)
            return False
        article.title = self.title_entry.get().strip()
        article.body = self.body_box.get("1.0", "end-1c").strip()
        article.image_url = self.image_entry.get().strip()
        article.image_caption = self.caption_entry.get().strip()
        article.image_credit = self.credit_entry.get().strip()
        article.areas = list(dict.fromkeys(x.strip() for x in self.areas_var.get().split(",") if x.strip()))
        article.category = self.category_var.get().strip()
        article.notify_readers = self.notify_var.get()
        article.notification_type = self.notification_type_var.get()
        article.notification_message = self.notification_message_entry.get().strip()
        self.store.upsert(article)
        self.status_label.configure(text="Local draft saved. Not published.")
        self._loaded_snapshot = self._editor_values()
        self._refresh()
        return True


def open_app_publishing(master):
    return AppPublishingWindow(master)
