"""Central review queue for newly discovered non-Planning content."""

from __future__ import annotations

from datetime import datetime
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import messagebox
import webbrowser

import customtkinter as ctk
from PIL import Image

from newsdesk.services.image_service import ImageService
from newsdesk.social.selection import add_story_to_social_desk
from newsdesk.social.store import SocialDraftStore
from newsdesk.theme import ACTION_BLUE, ACTION_BLUE_HOVER, APP_BG, BORDER, BRAND_RED, BRAND_RED_HOVER, CARD_BG, HEADER_BG, SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from newsdesk.ui_support import focus_existing_window, maximize_window
from newsdesk.updates.store import ELIGIBLE_MODULES, STATUS_METRICOOL, STATUS_NEW, STATUS_SOCIAL, UpdatesStore
from newsdesk.updates.content_gate import has_verified_full_content, is_materially_full


_active_window = None
ALL = "All"
STATUS_LABELS = {ALL: "", "New": STATUS_NEW, "Sent to Social Desk": STATUS_SOCIAL, "Sent to Metricool": STATUS_METRICOOL}
MODULE_LABELS = {"police": "Police", "fire": "Fire", "sport": "Sport", "council": "Council", "content": "Local Democracy"}


def get_updates_dashboard_summary() -> dict[str, int]:
    return UpdatesStore().summary()


def open_updates_desk(master=None):
    global _active_window
    if focus_existing_window(_active_window):
        return _active_window
    _active_window = UpdatesDesk(master)
    return _active_window


class UpdatesDesk(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Updates Desk — NewsDesk Pro")
        self.geometry("1500x900"); self.minsize(1120, 700); self.configure(fg_color=APP_BG)
        if master is not None: self.transient(master)
        self.store = UpdatesStore()
        self.items = []; self.selected = None
        self._detail_queue = Queue(); self._loading_item_id = ""
        self._image_jobs = 0
        self._image_service = ImageService(timeout=15); self._detail_image = None
        self.query_var = ctk.StringVar(); self.module_var = ctk.StringVar(value=ALL); self.status_var = ctk.StringVar(value=ALL)
        self._build(); self.refresh(); self.after(100, lambda: maximize_window(self))

    def _build(self):
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=105); header.pack(fill="x"); header.pack_propagate(False)
        ctk.CTkLabel(header, text="UPDATES DESK", font=("Arial", 28, "bold"), text_color=TEXT_PRIMARY).pack(side="left", padx=28)
        ctk.CTkLabel(header, text="New content from every refresh except Planning", text_color=TEXT_MUTED).pack(side="left")
        ctk.CTkButton(header, text="CLOSE", width=100, fg_color="#475569", command=self.destroy).pack(side="right", padx=24)
        filters = ctk.CTkFrame(self, fg_color="transparent"); filters.pack(fill="x", padx=24, pady=12)
        search = ctk.CTkEntry(filters, textvariable=self.query_var, placeholder_text="Search updates", width=300); search.pack(side="left", padx=(0, 8)); search.bind("<KeyRelease>", lambda _e: self.refresh())
        ctk.CTkOptionMenu(filters, variable=self.module_var, values=[ALL, *MODULE_LABELS.values()], width=180, command=lambda _v: self.refresh()).pack(side="left", padx=4)
        ctk.CTkOptionMenu(filters, variable=self.status_var, values=list(STATUS_LABELS), width=190, command=lambda _v: self.refresh()).pack(side="left", padx=4)
        ctk.CTkButton(filters, text="SET CURRENT AS BASELINE", width=190, fg_color="#475569", command=self.set_baseline).pack(side="right", padx=(8,0))
        ctk.CTkButton(filters, text="CLEAR COMPLETED", width=160, fg_color="#475569", command=self.clear_completed).pack(side="right")
        self.summary_label = ctk.CTkLabel(filters, text="", text_color=TEXT_SECONDARY); self.summary_label.pack(side="right", padx=16)
        body = ctk.CTkFrame(self, fg_color="transparent"); body.pack(fill="both", expand=True, padx=22, pady=(0,22)); body.grid_columnconfigure(0, weight=2); body.grid_columnconfigure(1, weight=3); body.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(body, fg_color=HEADER_BG, border_width=1, border_color=BORDER); left.grid(row=0,column=0,sticky="nsew",padx=(0,7))
        self.listbox = tk.Listbox(left, bg=CARD_BG, fg=TEXT_PRIMARY, selectbackground=BRAND_RED, selectforeground=TEXT_PRIMARY, borderwidth=0, highlightthickness=0, font=("Arial",16), activestyle="none", exportselection=False)
        scroll = ctk.CTkScrollbar(left, command=self.listbox.yview); self.listbox.configure(yscrollcommand=scroll.set); scroll.pack(side="right", fill="y", padx=(0,6), pady=10); self.listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10); self.listbox.bind("<<ListboxSelect>>", self._select)
        right = ctk.CTkFrame(body, fg_color=HEADER_BG, border_width=1, border_color=BORDER); right.grid(row=0,column=1,sticky="nsew",padx=(7,0))
        actions = ctk.CTkFrame(right, fg_color="transparent"); actions.pack(fill="x", padx=14, pady=12)
        self.send_button = ctk.CTkButton(actions, text="SEND TO SOCIAL DESK", fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER, command=self.send_to_social); self.send_button.pack(side="right")
        ctk.CTkButton(actions, text="DELETE", width=100, fg_color="#475569", command=self.delete_selected).pack(side="right", padx=8)
        ctk.CTkButton(actions, text="OPEN SOURCE", width=120, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.open_source).pack(side="right")
        self.load_button = ctk.CTkButton(actions, text="LOAD FULL CONTENT", width=155, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.load_full_content)
        self.load_button.pack(side="left")
        self.detail = ctk.CTkScrollableFrame(right, fg_color=CARD_BG); self.detail.pack(fill="both", expand=True, padx=14, pady=(0,14))

    def refresh(self):
        self.store.reconcile_social_drafts(SocialDraftStore().load())
        selected_module = next((key for key,value in MODULE_LABELS.items() if value == self.module_var.get()), "")
        self.items = self.store.list_items(status=STATUS_LABELS[self.status_var.get()], module_key=selected_module, query=self.query_var.get())
        self.listbox.delete(0,"end")
        for item in self.items:
            status = {STATUS_NEW:"NEW", STATUS_SOCIAL:"SENT TO SOCIAL DESK", STATUS_METRICOOL:"SENT TO METRICOOL"}[item.status]
            self.listbox.insert("end", f"{MODULE_LABELS[item.module_key]}  •  {status}\n{item.title}")
            if item.status in {STATUS_SOCIAL, STATUS_METRICOOL}:
                self.listbox.itemconfig(self.listbox.size() - 1, bg=BRAND_RED, fg=TEXT_PRIMARY)
        summary = self.store.summary(); self.summary_label.configure(text=f"{summary['new']} new  •  {summary['social']} social  •  {summary['metricool']} Metricool")
        self.selected = None; self._render_placeholder()

    def _select(self, _event=None):
        indexes = self.listbox.curselection()
        if not indexes or indexes[0] >= len(self.items): return
        self.selected = self.items[indexes[0]]; item = self.selected
        status = {STATUS_NEW:"NEW", STATUS_SOCIAL:"SENT TO SOCIAL DESK", STATUS_METRICOOL:"SENT TO METRICOOL"}[item.status]
        timestamps = []
        if item.social_sent_at: timestamps.append(f"Social Desk: {self._date(item.social_sent_at)}")
        if item.metricool_sent_at: timestamps.append(f"Metricool: {self._date(item.metricool_sent_at)}" + (f" • ID {item.metricool_id}" if item.metricool_id else ""))
        self._render_item(item, status, timestamps)
        complete = has_verified_full_content(item.module_key, item.story)
        self.send_button.configure(
            state="normal" if item.status == STATUS_NEW and complete else "disabled",
            text=(
                "SEND TO SOCIAL DESK" if item.status == STATUS_NEW and complete
                else "FULL CONTENT REQUIRED" if item.status == STATUS_NEW
                else status
            ),
        )
        self.load_button.configure(state="normal", text="LOAD FULL CONTENT")
        if item.status == STATUS_NEW and not complete:
            self.load_full_content(automatic=True)

    def _clear_detail(self):
        for child in self.detail.winfo_children(): child.destroy()
        self._detail_image = None

    def _render_placeholder(self):
        self._clear_detail()
        ctk.CTkLabel(self.detail, text="Select an update to review its full content and available image.", text_color=TEXT_MUTED).pack(pady=40)

    def _render_item(self, item, status, timestamps):
        self._clear_detail(); story = item.story
        ctk.CTkLabel(self.detail, text=item.title, font=("Arial",23,"bold"), text_color=TEXT_PRIMARY, anchor="w", justify="left", wraplength=700).pack(fill="x", padx=12, pady=(12,6))
        ctk.CTkLabel(self.detail, text=status, font=("Arial",12,"bold"), text_color=BRAND_RED if item.status != STATUS_NEW else SUCCESS, anchor="w").pack(fill="x", padx=12)
        metadata = f"{MODULE_LABELS[item.module_key]} • {item.source}\nPublished: {item.published or 'Not supplied'}\nFound: {self._date(item.discovered_at)}"
        if timestamps: metadata += "\n" + " | ".join(timestamps)
        ctk.CTkLabel(self.detail, text=metadata, text_color=TEXT_MUTED, anchor="w", justify="left").pack(fill="x", padx=12, pady=(4,12))
        if not has_verified_full_content(item.module_key, story):
            failure = str((story.extras or {}).get("updates_full_content_error") or "").strip()
            ctk.CTkLabel(
                self.detail,
                text=(
                    "FULL ARTICLE NOT AVAILABLE — transfer is locked"
                    + (f"\n{failure}" if failure else "")
                ),
                font=("Arial", 12, "bold"), text_color=BRAND_RED, anchor="w",
                justify="left", wraplength=700,
            ).pack(fill="x", padx=12, pady=(0, 10))
        if story.image_url:
            self._load_image_async(item.item_id, story.image_url, story.title)
        else:
            ctk.CTkLabel(self.detail, text="No source image supplied.", text_color=TEXT_MUTED, anchor="w").pack(fill="x", padx=12, pady=(0,8))
        ctk.CTkLabel(self.detail, text="ARTICLE CONTENT", font=("Arial",12,"bold"), text_color=TEXT_PRIMARY, anchor="w").pack(fill="x", padx=12, pady=(8,5))
        copy = str(story.body or story.summary or "No article copy was supplied by this refresh.").strip()
        ctk.CTkLabel(self.detail, text=copy, font=("Arial",15), text_color=TEXT_SECONDARY, anchor="w", justify="left", wraplength=700).pack(fill="x", padx=12, pady=(0,14))
        if story.image_caption or story.image_credit:
            caption = "\n".join(value for value in (story.image_caption, f"Credit: {story.image_credit}" if story.image_credit else "") if value)
            ctk.CTkLabel(self.detail, text=caption, text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=700).pack(fill="x", padx=12, pady=(0,10))
        ctk.CTkLabel(self.detail, text=f"SOURCE\n{item.source_url or 'No public source URL supplied'}", text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=700).pack(fill="x", padx=12, pady=(0,14))

    def _load_image_async(self, item_id, url, title):
        marker = ctk.CTkLabel(self.detail, text="Loading source image…", text_color=TEXT_MUTED, anchor="w")
        marker.pack(fill="x", padx=12, pady=(0,8))
        self._image_jobs += 1
        def worker():
            asset = self._image_service.get(url, fallback_title=title)
            self._detail_queue.put(("image", item_id, asset, marker))
        threading.Thread(target=worker, daemon=True, name="updates-image").start()
        self.after(100, self._poll_detail_queue)

    def load_full_content(self, automatic=False):
        if not self.selected or self._loading_item_id: return
        item = self.selected; self._loading_item_id = item.item_id
        self.load_button.configure(state="disabled", text="LOADING CONTENT…")
        def worker():
            try:
                if item.module_key == "content":
                    from contentdesk.collector import ContentExplorerCollector
                    from contentdesk.config import load_api_key
                    from contentdesk.storage import ContentStore
                    from modules.content import _story_from_row
                    article_id = item.story.story_id.rsplit(":",1)[-1]
                    content_store = ContentStore(); row = content_store.get(article_id)
                    if row is None or not int(row["detail_complete"] or 0):
                        key = load_api_key()
                        if not key: raise RuntimeError("The LDRS API key is not configured.")
                        with ContentExplorerCollector(key) as collector: detail = collector.fetch_detail(article_id)
                        content_store.upsert_many([detail]); row = content_store.get(article_id)
                    story = _story_from_row(row)
                    if not is_materially_full(story):
                        raise RuntimeError("The LDRS record did not supply a substantive full article body.")
                elif item.module_key == "sport":
                    from newsdesk.services.sport_article_service import SportArticleService
                    from newsdesk.story import Story
                    story = Story.from_dict(item.story.to_dict())
                    teaser = str(story.summary or story.body or "").strip()
                    result = SportArticleService(timeout=30).enrich(story)
                    if not result.successful or not is_materially_full(story, teaser=teaser):
                        detail = result.error or "The source supplied only its feed teaser; no full article text was found."
                        raise RuntimeError(detail)
                else:
                    from newsdesk.sources.article_scraper import ArticleScraper
                    if not item.source_url: raise RuntimeError("No public source URL is available.")
                    result = ArticleScraper(timeout=30).extract_article(item.source_url, "")
                    from newsdesk.story import Story
                    story = Story.from_dict(item.story.to_dict())
                    teaser = str(story.summary or story.body or "").strip()
                    extracted = str(result.get("text") or "").strip()
                    if extracted: story.body = extracted
                    if not is_materially_full(story, teaser=teaser):
                        raise RuntimeError("The source supplied only a teaser; no substantive full article text was found.")
                    if str(result.get("image") or "").strip(): story.image_url = str(result["image"]).strip()
                    if str(result.get("author") or "").strip(): story.author = str(result["author"]).strip()
                    story.extras["updates_full_content_verified"] = True
                story.extras.pop("updates_full_content_error", None)
                self.store.update_story(item.item_id, story)
                self._detail_queue.put(("content", item.item_id, None, None))
            except Exception as exc:
                try:
                    from newsdesk.story import Story
                    failed_story = Story.from_dict(item.story.to_dict())
                    failed_story.extras["updates_full_content_error"] = str(exc)
                    self.store.update_story(item.item_id, failed_story)
                except Exception:
                    pass
                self._detail_queue.put(("error", item.item_id, str(exc), automatic))
        threading.Thread(target=worker, daemon=True, name="updates-full-content").start()
        self.after(100, self._poll_detail_queue)

    def _poll_detail_queue(self):
        try:
            while True:
                kind, item_id, value, extra = self._detail_queue.get_nowait()
                if kind == "image":
                    self._image_jobs = max(0, self._image_jobs - 1)
                    asset, marker = value, extra
                    try:
                        visible = self.selected and self.selected.item_id == item_id and marker.winfo_exists()
                    except tk.TclError:
                        visible = False
                    if visible:
                        if asset.available and not asset.is_fallback:
                            picture = Image.open(asset.local_path); picture.thumbnail((700,340))
                            self._detail_image = ctk.CTkImage(light_image=picture, dark_image=picture, size=picture.size)
                            marker.configure(text="", image=self._detail_image)
                        else: marker.configure(text="Source image unavailable.")
                elif kind == "content":
                    self._loading_item_id = ""; self._reload_selected(item_id)
                elif kind == "error":
                    self._loading_item_id = ""; self.load_button.configure(state="normal", text="LOAD FULL CONTENT")
                    self._reload_selected(item_id)
                    if not extra:
                        messagebox.showerror("Load full content", value, parent=self)
        except Empty: pass
        if self._loading_item_id or self._image_jobs or not self._detail_queue.empty(): self.after(100, self._poll_detail_queue)

    def _reload_selected(self, item_id):
        refreshed = next((item for item in self.store.list_items() if item.item_id == item_id), None)
        if refreshed is None: self.refresh(); return
        self.selected = refreshed
        status = {STATUS_NEW:"NEW", STATUS_SOCIAL:"SENT TO SOCIAL DESK", STATUS_METRICOOL:"SENT TO METRICOOL"}[refreshed.status]
        timestamps = []
        if refreshed.social_sent_at: timestamps.append(f"Social Desk: {self._date(refreshed.social_sent_at)}")
        if refreshed.metricool_sent_at: timestamps.append(f"Metricool: {self._date(refreshed.metricool_sent_at)}")
        complete = has_verified_full_content(refreshed.module_key, refreshed.story)
        self._render_item(refreshed, status, timestamps)
        self.load_button.configure(
            state="normal",
            text="REFRESH FULL CONTENT" if complete else "LOAD FULL CONTENT",
        )
        self.send_button.configure(
            state="normal" if refreshed.status == STATUS_NEW and complete else "disabled",
            text=(
                "SEND TO SOCIAL DESK"
                if refreshed.status == STATUS_NEW and complete
                else "FULL CONTENT REQUIRED"
                if refreshed.status == STATUS_NEW
                else status
            ),
        )

    @staticmethod
    def _date(value):
        try: return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y %H:%M")
        except (TypeError, ValueError): return str(value or "")

    def open_source(self):
        if self.selected and self.selected.source_url: webbrowser.open(self.selected.source_url)

    def send_to_social(self):
        if not self.selected or self.selected.status != STATUS_NEW: return
        if not has_verified_full_content(self.selected.module_key, self.selected.story):
            messagebox.showwarning(
                "Full content required",
                "This item cannot be sent because a substantive full article has not been obtained.",
                parent=self,
            )
            return
        try:
            draft = add_story_to_social_desk(
                self, self.selected.story,
                module_key=self.selected.module_key,
                updates_item_id=self.selected.item_id,
            )
        except Exception as exc:
            messagebox.showerror(
                "Send to Social Desk",
                f"The item could not be sent to Social Desk.\n\n{exc}",
                parent=self,
            )
            return
        if draft is None: return
        try: self.store.mark_social(self.selected.item_id, draft.draft_id)
        except ValueError as exc: messagebox.showwarning("Updates Desk", str(exc), parent=self)
        self.refresh()

    def delete_selected(self):
        if not self.selected: return
        if not messagebox.askyesno("Updates Desk", "Remove this update from Updates Desk? It will not return after a later refresh.", parent=self): return
        self.store.delete(self.selected.item_id); self.refresh()

    def clear_completed(self):
        if not messagebox.askyesno("Updates Desk", "Remove all items confirmed as sent to Metricool? They will not return after later refreshes.", parent=self): return
        count = self.store.clear_completed(); self.refresh(); messagebox.showinfo("Updates Desk", f"Removed {count} completed item(s).", parent=self)

    def set_baseline(self):
        if not messagebox.askyesno("Set current baseline", "Remove every currently NEW item from the visible queue? They will be remembered and will not return. Only genuinely unseen items found by later refreshes will then appear.", parent=self): return
        count = self.store.set_current_as_baseline(); self.refresh(); messagebox.showinfo("Updates Desk", f"Baseline set. Removed {count} existing item(s) from the queue.", parent=self)


__all__ = ["get_updates_dashboard_summary", "open_updates_desk"]
