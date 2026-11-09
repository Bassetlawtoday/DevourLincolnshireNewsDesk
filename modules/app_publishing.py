"""Devour News App Publishing: local editorial review screen.

No public publishing occurs until a cloud endpoint has been agreed and built.
"""
from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
from PIL import Image, ImageTk
from io import BytesIO
from pathlib import Path
import time
from threading import Thread
from urllib.parse import urlparse
from urllib.request import urlopen, Request
import queue
import webbrowser
import textwrap
import shutil
import json
import os
import hashlib
import hmac
import getpass
from datetime import datetime

from newsdesk.app_publishing.store import AppArticleStore
from newsdesk.app_publishing.mobile_payload import write_export, ready_payload
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
        self.geometry("1450x900")
        self.minsize(1080, 700)
        self.configure(fg_color=BG)
        self.store = AppArticleStore()
        self.current_id = None
        self._loaded_snapshot = None
        self._preview_token = 0
        self._preview_started = 0.0
        self._preview_local_path = ''
        self._preview_image = None
        self._preview_results = queue.Queue()
        self._preview_status = 'Idle'
        self._upload_in_progress = False
        self._uploaded_receipts_path = self.store.path.parent / "uploaded_article_receipts.json"
        self.search_var = ctk.StringVar()
        self.review_filter_var = ctk.StringVar(value="All")
        self.review_status = "new"
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
        ctk.CTkLabel(self, text="Private Supabase uploads available - public publishing and withdrawal not connected", text_color=MUTED).pack(anchor="w", padx=22)
        layout = ctk.CTkFrame(self, fg_color="transparent")
        layout.pack(fill="both", expand=True, padx=18, pady=15)
        layout.grid_columnconfigure(0, weight=0, minsize=340)
        layout.grid_columnconfigure(1, weight=1)
        layout.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(layout, fg_color=PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.configure(width=340)
        left.grid_propagate(False)
        ctk.CTkEntry(left, textvariable=self.search_var, placeholder_text="Search incoming articles").pack(fill="x", padx=10, pady=10)
        self.search_var.trace_add("write", lambda *_: self._refresh())
        ctk.CTkOptionMenu(left, variable=self.review_filter_var,
                          values=["All", "New", "Draft", "Ready"],
                          command=lambda _value: self._refresh()).pack(fill="x", padx=10, pady=(0, 6))
        self.review_counts_label = ctk.CTkLabel(left, text="", text_color=MUTED)
        self.review_counts_label.pack(anchor="w", padx=10, pady=(0, 5))
        ctk.CTkButton(left, height=36, text="DELETE SELECTED ARTICLE", fg_color="#9a3412", hover_color="#7c2d12", command=self._delete_selected).pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkButton(left, height=36, text="CLEAR ALL APP ARTICLES", fg_color="#991b1b", hover_color="#7f1d1d", command=self._clear_all).pack(fill="x", padx=10, pady=(0, 6))
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
        self.image_preview = tk.Label(form, text="No image selected", fg=TEXT, bg=PANEL, height=7, anchor="center")
        self.image_preview.pack(anchor="w", pady=(8, 3))
        self.preview_status_label = ctk.CTkLabel(form, text="Image status: Not loaded", text_color=MUTED)
        self.preview_status_label.pack(anchor="w")
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
        self.quality_label = ctk.CTkLabel(right, text="Editorial checks: Select an article", text_color=MUTED, justify="left", anchor="w", wraplength=850)
        self.quality_label.pack(fill="x", padx=14, pady=(4, 0))
        controls = ctk.CTkFrame(right, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=(8, 4))
        controls.grid_columnconfigure((0, 1, 2), weight=1, uniform="actions")
        ctk.CTkButton(controls, text="SAVE DRAFT", height=36, command=self._save, fg_color=BLUE).grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.ready_button = ctk.CTkButton(controls, text="MARK AS READY", height=36, command=self._mark_ready)
        self.ready_button.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self.upload_button = ctk.CTkButton(controls, text="UPLOAD READY ARTICLE", height=36, command=self._upload_ready_article)
        self.upload_button.grid(row=0, column=2, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(controls, text="EXPORT READY PREVIEW", height=36, command=self._export_ready_preview).grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(controls, text="TEST SUPABASE CONNECTION", height=36, command=self._test_supabase_connection).grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(controls, text="CLOUD DELETE (AWAITING SECURE API)", height=36, state="disabled").grid(row=1, column=2, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(controls, text="PUBLISH (NOT CONNECTED)", height=36, state="disabled").grid(row=2, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(controls, text="WITHDRAW (NOT CONNECTED)", height=36, state="disabled").grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        ctk.CTkLabel(controls, text="Local deletion never removes a Supabase copy.", text_color=MUTED).grid(row=2, column=2, sticky="w", padx=6)
        self.status_label = ctk.CTkLabel(right, text="Select an article to edit", text_color=MUTED)
        self.status_label.pack(anchor="w", padx=14, pady=(0, 10))

    @staticmethod
    def _entry(parent, label):
        ctk.CTkLabel(parent, text=label, text_color=TEXT).pack(anchor="w", pady=(8, 3))
        entry = ctk.CTkEntry(parent)
        entry.pack(fill="x")
        return entry

    @staticmethod
    def _review_state(article):
        value = (article.status or "").strip().lower()
        return value if value in {"new", "draft", "ready"} else "draft"

    def _refresh(self):
        for child in self.list_box.winfo_children():
            child.destroy()
        try:
            articles = self.store.load()
        except (OSError, ValueError) as error:
            messagebox.showerror("App Publishing", str(error), parent=self)
            return
        counts = {state: sum(self._review_state(item) == state for item in articles)
                  for state in ("new", "draft", "ready")}
        self.review_counts_label.configure(
            text=f"New: {counts['new']}   Draft: {counts['draft']}   Ready: {counts['ready']}"
        )
        query = self.search_var.get().strip().casefold()
        selected = self.review_filter_var.get().casefold()
        for article in sorted(articles, key=lambda item: item.updated_at, reverse=True):
            state = self._review_state(article)
            if selected != "all" and selected != state:
                continue
            if query and query not in (article.title + " " + article.body).casefold():
                continue
            headline = article.title or "Untitled"
            wrapped = textwrap.fill(headline, width=36, max_lines=3, placeholder="...")
            cloud_marker = " [UPLOADED]" if article.article_id in self._local_upload_receipts() else ""
            ctk.CTkButton(
                self.list_box, text=f"[{state.upper()}]{cloud_marker}  {wrapped}",
                anchor="w", fg_color="#334155", height=84,
                font=("Arial", 14),
                command=lambda item=article: self._open_article(item),
            ).pack(fill="x", pady=3)

    def _local_upload_receipts(self):
        """Local upload confirmations; not a live cloud inventory."""
        try:
            with self._uploaded_receipts_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, OSError, ValueError):
            return {}

    def _record_uploaded_receipt(self, article_id):
        receipts = self._local_upload_receipts()
        receipts[article_id] = datetime.now().astimezone().isoformat()
        path = self._uploaded_receipts_path
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_suffix(".tmp")
        try:
            with staged.open("w", encoding="utf-8") as handle:
                json.dump(receipts, handle, indent=2)
            staged.replace(path)
        finally:
            if staged.exists():
                staged.unlink()

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

    def _set_preview_status(self, status, detail=""):
        self._preview_status = status
        self.preview_status_label.configure(
            text="Image status: " + status + ((" - " + detail[:110]) if detail else "")
        )

    def _poll_preview(self):
        # A failed preview must never permanently stop the queue polling loop.
        try:
            for _ in range(20):
                try:
                    token, result, error = self._preview_results.get_nowait()
                except queue.Empty:
                    break
                if token == "upload":
                    self._upload_in_progress = False
                    self.upload_button.configure(state="normal")
                    self.status_label.configure(text=error)
                    if result and isinstance(result, str):
                        try:
                            self._record_uploaded_receipt(result)
                            self._refresh()
                        except (OSError, ValueError) as exc:
                            error += "\\n\\nLocal receipt not saved: " + str(exc)
                    (messagebox.showinfo if result else messagebox.showerror)("Secure article upload", error, parent=self)
                    continue
                if token == "connection":
                    self.status_label.configure(text=error)
                    if result:
                        messagebox.showinfo("Supabase connection", error, parent=self)
                    else:
                        messagebox.showerror("Supabase connection", error, parent=self)
                    continue
                if token != self._preview_token:
                    continue
                self._preview_started = 0.0
                if error:
                    self.image_preview.configure(image="", text="Image unavailable")
                    self._set_preview_status("Download failed", error)
                else:
                    try:
                        # Explicitly bind the Tk image to this label's interpreter.
                        # CTkImage can otherwise create a PhotoImage on the default
                        # root, which fails in a separate CTkToplevel window.
                        preview = ImageTk.PhotoImage(result, master=self.image_preview)
                        self._preview_image = preview
                        self.image_preview.configure(image=preview, text="", height=0)
                        self._set_preview_status("Loaded")
                    except Exception as exc:
                        self.image_preview.configure(image="", text="Image unavailable")
                        self._set_preview_status("Display failed", str(exc))
        except Exception as exc:
            # Even a Tk display error must not silently kill future polling.
            try:
                self._set_preview_status("Display failed", str(exc))
            except Exception:
                pass
        finally:
            try:
                if self.winfo_exists():
                    self.after(150, self._poll_preview)
            except Exception:
                pass

    def _preview_timeout(self, token):
        if token != self._preview_token or not self._preview_started:
            return
        self._preview_started = 0.0
        self._preview_token += 1
        self.image_preview.configure(image="", text="Image preview timed out")
        self._set_preview_status("Timed out", "No response within 10 seconds")

    def _load_preview(self):
        self._preview_token += 1
        token = self._preview_token
        self._preview_image = None
        self._preview_started = time.monotonic()
        self.image_preview.configure(image="", text="Loading image preview...", height=7)
        self._set_preview_status("Loading")
        url = self.image_entry.get().strip()
        local_path = self._preview_local_path
        parsed = urlparse(url)
        if "placeholder" in parsed.path.casefold():
            self._preview_started = 0.0
            self.image_preview.configure(image="", text="No story photograph supplied")
            self._set_preview_status("Missing", "Source placeholder")
            return
        if (parsed.scheme != "https" or not parsed.netloc) and not local_path:
            self._preview_started = 0.0
            self.image_preview.configure(image="", text="No valid image available")
            self._set_preview_status("Missing", "No local file or HTTPS image URL")
            return

        # Schedule a separate one-shot timeout on the GUI event loop.
        # Image filesystem checks, decoding and network access stay in the worker.
        self.after(10000, lambda requested=token: self._preview_timeout(requested))

        def fetch():
            local_error = None
            if local_path:
                try:
                    path = Path(local_path)
                    if path.is_file():
                        with Image.open(path) as img:
                            img.thumbnail((500, 250))
                            img.load()
                            self._preview_results.put((token, img.copy(), None))
                            return
                except Exception as exc:
                    local_error = str(exc)
            if parsed.scheme != "https" or not parsed.netloc:
                self._preview_results.put(
                    (token, None, local_error or "No HTTPS fallback URL")
                )
                return
            try:
                with urlopen(url, timeout=6) as response:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if not content_type.startswith("image/"):
                        raise ValueError("Source did not return an image")
                    data = response.read(5_000_001)
                    if len(data) > 5_000_000:
                        raise ValueError("Image exceeds 5 MB limit")
                with Image.open(BytesIO(data)) as img:
                    img.thumbnail((500, 250))
                    img.load()
                    result = img.copy()
                self._preview_results.put((token, result, None))
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
        self.review_status = self._review_state(article)
        self.ready_button.configure(text="RETURN TO DRAFT" if self.review_status == "ready" else "MARK AS READY")
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
        self._preview_local_path = article.image_local_path or ""
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
        self._update_quality()
        receipt = self._local_upload_receipts().get(article.article_id)
        cloud_status = ("Uploaded privately (local receipt: " + receipt + ")" if receipt else
                        "No upload recorded locally; cloud status not verified")
        self.status_label.configure(text=f"Editing {self.review_status.upper()} article: {article.title} | {cloud_status}")

    @staticmethod
    def _set_entry(entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def _count_words(self):
        words = len(self.body_box.get("1.0", "end-1c").split())
        self.counter.configure(text=f"{words} words (approximately 500 target)")

    def _quality_warnings(self):
        warnings = []
        title = self.title_entry.get().strip()
        body = self.body_box.get("1.0", "end-1c").strip()
        if not title:
            warnings.append("Headline missing")
        if not body:
            warnings.append("Article body missing")
        elif len(body.split()) < 200:
            warnings.append("Short article (under 200 words; review recommended)")
        if not self.category_var.get().strip():
            warnings.append("Category missing")
        if not self.areas_var.get().strip():
            warnings.append("No specific town/area (countywide may be appropriate)")
        image_url = self.image_entry.get().strip()
        if not image_url and not self._preview_local_path:
            warnings.append("No photograph (optional)")
        elif not self.credit_entry.get().strip():
            warnings.append("Image credit missing; check rights before publication")
        return warnings

    def _update_quality(self):
        if not self.current_id:
            self.quality_label.configure(text="Editorial checks: Select an article")
            return
        warnings = self._quality_warnings()
        self.quality_label.configure(text=("Editorial checks: No warnings" if not warnings else
                                          "Editorial checks (review before publishing): " + " | ".join(warnings)))

    def _delete_selected(self):
        """Delete one local App Publishing article, never the source or cloud copy."""
        if self._upload_in_progress:
            messagebox.showwarning("App Publishing", "Wait until the current upload finishes.", parent=self)
            return
        if not self.current_id:
            messagebox.showinfo("App Publishing", "Select an article to delete.", parent=self)
            return
        try:
            articles = self.store.load()
            selected = next((item for item in articles if item.article_id == self.current_id), None)
        except (OSError, ValueError) as exc:
            messagebox.showerror("App Publishing", str(exc), parent=self)
            return
        if selected is None:
            messagebox.showerror("App Publishing", "This article is no longer in App Publishing.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete selected article locally",
            f"Delete this {self._review_state(selected).upper()} article from App Publishing?\\n\\n"
            f"{selected.title}\\n\\n"
            "Any copy already stored or published in Supabase will remain untouched.\\n"
            "Original stories in NewsDesk collection modules will remain untouched.\\n\\n"
            "A dated backup will be created before deletion.",
            icon="warning", parent=self,
        ):
            return
        try:
            backup_dir = self.store.path.parent / "individual_delete_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / ("drafts-before-delete-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
            if self.store.path.exists():
                shutil.copy2(self.store.path, backup)
            self.store.save([item for item in articles if item.article_id != selected.article_id])
        except (OSError, ValueError) as exc:
            messagebox.showerror("App Publishing", "Deletion cancelled: " + str(exc), parent=self)
            return
        self.current_id = None
        self._loaded_snapshot = None
        self.review_status = "new"
        self._preview_token += 1
        self._preview_started = 0.0
        self._preview_local_path = ""
        self._preview_image = None
        self.image_preview.configure(image="", text="No image selected", height=7)
        self._set_preview_status("Not loaded")
        for entry in (self.title_entry, self.image_entry, self.caption_entry,
                      self.credit_entry, self.notification_message_entry):
            self._set_entry(entry, "")
        self.body_box.delete("1.0", "end")
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.configure(state="disabled")
        self.source_url = ""
        self.source_label.configure(text="Source: -")
        self.areas_var.set("")
        self.category_var.set("")
        self.notify_var.set(False)
        self.ready_button.configure(text="MARK AS READY")
        self._update_quality()
        self._count_words()
        self._refresh()
        self.status_label.configure(text=f"Deleted locally: {selected.title}. Cloud copy untouched. Backup: {backup}")

    def _clear_all(self):
        try:
            count = len(self.store.load())
        except (OSError, ValueError) as exc:
            messagebox.showerror("App Publishing", str(exc), parent=self)
            return
        if not count:
            messagebox.showinfo("App Publishing", "There are no articles to clear.", parent=self)
            return
        if not messagebox.askyesno("CLEAR ALL App Publishing articles",
            f"Delete ALL {count} App Publishing articles, including New, Draft and Ready?\\n\\n"
            "This does not delete stories in their original NewsDesk modules.\\n"
            "A dated backup will be created before deletion.", icon="warning", parent=self):
            return
        try:
            backup_dir = self.store.path.parent / "clear_all_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / ("drafts-before-clear-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
            if self.store.path.exists():
                shutil.copy2(self.store.path, backup)
            self.store.save([])
        except (OSError, ValueError) as exc:
            messagebox.showerror("App Publishing", "Clear cancelled: " + str(exc), parent=self)
            return
        self.current_id = None
        self._loaded_snapshot = None
        self.review_status = "new"
        self._preview_token += 1
        self._preview_started = 0.0
        self._preview_local_path = ""
        self._preview_image = None
        self.image_preview.configure(image="", text="No image selected", height=7)
        self._set_preview_status("Not loaded")
        for entry in (self.title_entry, self.image_entry, self.caption_entry,
                      self.credit_entry, self.notification_message_entry):
            self._set_entry(entry, "")
        self.body_box.delete("1.0", "end")
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.configure(state="disabled")
        self.source_url = ""
        self.source_label.configure(text="Source: -")
        self.areas_var.set("")
        self.category_var.set("")
        self.notify_var.set(False)
        self.review_filter_var.set("All")
        self.search_var.set("")
        self.ready_button.configure(text="MARK AS READY")
        self._update_quality()
        self._count_words()
        self._refresh()
        self.status_label.configure(text=f"Cleared {count} App Publishing articles. Backup: {backup}")
        messagebox.showinfo("App Publishing", f"Cleared {count} articles.\\nBackup: {backup}", parent=self)

    def _upload_ready_article(self):
        """Explicit, authenticated private upload of one saved Ready article."""
        if self._upload_in_progress:
            return
        if not self.current_id:
            messagebox.showinfo("Secure article upload", "Select a Ready article first.", parent=self)
            return
        try:
            article = next((a for a in self.store.load() if a.article_id == self.current_id), None)
            if article is None or self._review_state(article) != "ready":
                messagebox.showwarning("Secure article upload", "Only saved Ready articles can be uploaded.", parent=self)
                return
            if self._loaded_snapshot is None or self._editor_values() != self._loaded_snapshot:
                messagebox.showwarning("Secure article upload", "Save your changes before uploading.", parent=self)
                return
            payload = ready_payload(article)
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if len(data) > 100000:
                raise ValueError("Article exceeds the 100 KB upload limit.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Secure article upload", str(exc), parent=self)
            return
        token = os.environ.get("NEWSDESK_UPLOAD_TOKEN", "").strip()
        if not token:
            messagebox.showerror(
                "Secure article upload",
                "Upload token not configured. Set NEWSDESK_UPLOAD_TOKEN in your Windows user environment and restart NewsDesk Pro.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Upload Ready article privately",
            f"Upload this Ready article to the private Devour News database?\\n\\n{article.title}\\n\\n"
            "This will NOT publish it or send notifications. An existing cloud record with the same article ID will be updated.",
            parent=self,
        ):
            return
        self._upload_in_progress = True
        self.upload_button.configure(state="disabled")
        self.status_label.configure(text="Uploading Ready article privately...")
        def worker():
            try:
                endpoint = ("https://onmmfbyocbnwbqxmdthe.supabase.co"
                            "/functions/v1/newsdesk-article-upload")
                request = Request(endpoint, data=data, method="POST", headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "x-newsdesk-token": token,
                })
                with urlopen(request, timeout=20) as response:
                    raw = response.read(8193)
                    if len(raw) > 8192:
                        raise ValueError("Upload response too large")
                    result = json.loads(raw.decode("utf-8"))
                    if (response.status != 200
                        or result.get("status") != "stored_privately"
                        or result.get("article_id") != article.article_id
                        or result.get("published") is not False
                        or result.get("notification_sent") is not False):
                        raise ValueError("Unexpected upload confirmation")
                success = True
                message = "Article stored privately in Supabase. Not published; no notification sent."
            except Exception as exc:
                success = False
                message = "Upload failed: " + str(exc)
            self._preview_results.put(("upload", article.article_id if success else None, message))
        Thread(target=worker, daemon=True).start()

    def _test_supabase_connection(self):
        """Check the public, read-only Edge Function without credentials or article data."""
        endpoint = ("https://onmmfbyocbnwbqxmdthe.supabase.co"
                    "/functions/v1/newsdesk-connection-test")
        self.status_label.configure(text="Testing Supabase connection...")
        def worker():
            try:
                request = Request(endpoint, headers={"Accept": "application/json"}, method="GET")
                with urlopen(request, timeout=8) as response:
                    if response.status != 200:
                        raise ValueError(f"HTTP {response.status}")
                    data = response.read(8193)
                    if len(data) > 8192:
                        raise ValueError("Response too large")
                import json
                payload = json.loads(data.decode("utf-8"))
                if (payload.get("application") != "Devour News"
                    or payload.get("status") != "connection_ok"
                    or payload.get("database_access") is not False
                    or payload.get("publishing_enabled") is not False):
                    raise ValueError("Unexpected connection-test response")
                result = "Supabase connection successful. No articles uploaded or published."
                success = True
            except Exception as exc:
                result = "Supabase connection failed: " + str(exc)
                success = False
            self._preview_results.put(("connection", success, result))
        Thread(target=worker, daemon=True).start()

    def _export_ready_preview(self):
        """Export a local test feed; never send content to a server."""
        try:
            destination = self.store.path.parent / "mobile_preview" / "ready_articles.json"
            count = write_export(self.store.load(), destination)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Mobile preview export", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Mobile preview export",
            f"Prepared {count} Ready articles for offline testing.\\n\\n"
            f"File: {destination}\\n\\nNothing was published or uploaded.",
            parent=self,
        )

    def _mark_ready(self):
        if not self.current_id:
            messagebox.showinfo("App Publishing", "Select an article first.", parent=self)
            return
        if self.review_status == "ready":
            self._save(status="draft")
            return
        if not self.title_entry.get().strip() or not self.body_box.get("1.0", "end-1c").strip():
            messagebox.showwarning("App Publishing", "A headline and article body are required before marking ready.", parent=self)
            return
        warnings = self._quality_warnings()
        if warnings and not messagebox.askyesno("Editorial quality review",
            "Review these points before marking Ready:\\n\\n" + "\\n".join("- " + item for item in warnings) +
            "\\n\\nMark Ready anyway? (Nothing will be published.)", parent=self):
            return
        self._save(status="ready")

    def _save(self, status=None):
        if not self.current_id:
            messagebox.showinfo("App Publishing", "Select an article first.", parent=self)
            return False
        articles = self.store.load()
        article = next((item for item in articles if item.article_id == self.current_id), None)
        if article is None:
            messagebox.showerror("App Publishing", "The selected draft no longer exists.", parent=self)
            return False
        status = status or self._review_state(article)
        if status == "new":
            status = "draft"
        article.status = status
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
        self.review_status = status
        self.ready_button.configure(text="RETURN TO DRAFT" if status == "ready" else "MARK AS READY")
        self.status_label.configure(text=("Marked READY for future publishing. Not published." if status == "ready" else "Local draft saved. Not published."))
        self._loaded_snapshot = self._editor_values()
        self._update_quality()
        self._refresh()
        return True


def open_app_publishing(master):
    return AppPublishingWindow(master)
