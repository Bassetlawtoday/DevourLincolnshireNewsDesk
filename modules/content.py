"""LDRS Local Democracy Intelligence workspace for NewsDesk Pro."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import webbrowser

import customtkinter as ctk
from PIL import Image

from contentdesk.collector import ContentExplorerCollector, ContentExplorerError, _detail_body_lines
from contentdesk.config import CredentialError, has_api_key, load_api_key, load_settings, save_api_key, save_settings
from contentdesk.storage import ContentStore, decode_list
from newsdesk.header import NewsDeskHeader
from newsdesk.geography.lincolnshire import match_lincolnshire
from newsdesk.rich_clipboard import copy_rich_article
from newsdesk.services.image_service import ImageService
from newsdesk.story import Story
from newsdesk.theme import ACTION_BLUE, ACTION_BLUE_HOVER, ACCENT, APP_BG, BORDER, CARD_BG, HEADER_BG, SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from newsdesk.ui_support import DEFAULT_SEARCH_DEBOUNCE_MS, DebouncedAction, IntelligenceWindowSupport, focus_existing_window, maximize_window


ALL = "All"
SCOPE_LIMITS = {"Latest 100": 100, "Latest 500": 500, "All accessible": None}
_active_window = None


def _row_date(row) -> datetime | None:
    raw = str(row["created_at"] or "").strip()
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _display_date(row) -> str:
    value = _row_date(row)
    return value.strftime("%d/%m/%Y %H:%M") if value else str(row["created_at"] or "")


def _image_subject(caption: str, fallback: str = "") -> str:
    """Return the descriptive subject before LDRS credit/rights wording."""
    value = " ".join(str(caption or "").split()).strip()
    if not value:
        return str(fallback or "").strip()
    for marker in (". Credit:", " Credit:", ". Permission for", " Permission for"):
        if marker.casefold() in value.casefold():
            index = value.casefold().index(marker.casefold())
            value = value[:index].strip().rstrip(".")
            break
    return value or str(fallback or "").strip()


def _clean_article_copy(value: str, title: str = "") -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    return "\n\n".join(_detail_body_lines(lines, title, len(lines))).strip()


def _needs_detail_refresh(row) -> bool:
    """Refresh records created before attachment metadata was parsed correctly."""

    if not int(row["detail_complete"] or 0) or not str(row["body"] or "").strip():
        return True
    lines = [line.strip().casefold() for line in str(row["body"] or "").splitlines() if line.strip()]
    duplicated_lead = len(lines) > 1 and lines[0] == lines[1]
    weak_credit = bool(str(row["image_url"] or "").strip()) and str(
        row["image_credit"] or ""
    ).strip().casefold() in {"", "ldrs"}
    return duplicated_lead or weak_credit


def _row_is_lincolnshire(row) -> bool:
    """Keep the workspace and analytics scoped to Greater Lincolnshire."""

    return match_lincolnshire(
        (
            " ".join(decode_list(row["authorities_json"])),
            row["title"], row["slug"], row["summary"], row["body"],
        )
    ).matched


def _story_from_row(row) -> Story:
    authorities = decode_list(row["authorities_json"])
    categories = decode_list(row["categories_json"])
    body = _clean_article_copy(
        str(row["body"] or row["summary"] or row["slug"] or ""),
        str(row["title"] or row["slug"] or ""),
    )
    summary = str(row["summary"] or body).strip()
    image_caption = str(row["image_caption"] or "").strip()
    image_subject = _image_subject(image_caption, str(row["title"] or row["slug"] or "LDRS story image"))
    return Story(
        story_id=f"content:{row['article_id']}",
        title=str(row["slug"] or row["title"] or "").strip(),
        summary=summary,
        body=body,
        source="LDRS Content Explorer",
        url=str(row["source_url"] or "").strip(),
        published=str(row["created_at"] or "").strip(),
        author=str(row["author"] or "").strip(),
        location=", ".join(authorities),
        category="Local Democracy",
        image_url=str(row["image_url"] or "").strip(),
        image_caption=image_caption,
        # The complete LDRS caption contains both the named subject and the
        # mandatory credit/permission wording.  Keep it intact through the
        # central image library and Newsletter/Ghost output.
        image_credit=str(row["image_credit"] or image_caption or "LDRS").strip(),
        image_alt_text=image_subject,
        tags=[*authorities, *categories],
        extras={
            "content_type": str(row["content_type"] or "Story"),
            "author_email": str(row["author_email"] or ""),
            "reviewer_email": str(row["reviewer_email"] or ""),
            "authorities": authorities,
            "categories": categories,
            "image_title": image_subject,
        },
    )


def get_content_dashboard_summary() -> dict:
    try:
        summary = ContentStore().summary()
    except OSError:
        summary = {"count": 0, "updated": "Never"}
    summary["status"] = "API key configured" if has_api_key() else "API key required"
    return summary


def open_content(master=None):
    global _active_window
    if focus_existing_window(_active_window):
        return _active_window
    _active_window = ContentIntelligenceWindow(master)
    return _active_window


class ContentAnalyticsWindow(ctk.CTkToplevel):
    def __init__(self, parent, rows):
        super().__init__(parent)
        self.title("Local Democracy Intelligence Analytics")
        self.geometry("1050x760")
        self.minsize(820, 600)
        self.configure(fg_color=APP_BG)
        self.transient(parent)
        self.rows = list(rows)
        self.store = ContentStore()
        self.group_var = ctk.StringVar(value="Area")
        self._data = []
        top = ctk.CTkFrame(self, fg_color=HEADER_BG)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="LOCAL DEMOCRACY ANALYTICS", font=("Arial", 24, "bold"), text_color=TEXT_PRIMARY).pack(side="left", padx=20, pady=18)
        ctk.CTkButton(top, text="EXPORT CSV", fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.export_csv).pack(side="right", padx=(8, 20))
        ctk.CTkButton(top, text="CLOSE", fg_color="#374151", command=self.destroy).pack(side="right")
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(controls, text="GROUP BY", text_color=TEXT_MUTED, font=("Arial", 11, "bold")).pack(side="left", padx=(0, 8))
        ctk.CTkOptionMenu(controls, variable=self.group_var, values=["Area", "Author", "Category", "Type"], width=190, command=lambda _v:self.refresh()).pack(side="left")
        self.total = ctk.CTkLabel(controls, text="", text_color=TEXT_SECONDARY, font=("Arial", 13, "bold"))
        self.total.pack(side="right")
        shell = ctk.CTkFrame(self, fg_color=HEADER_BG, border_width=1, border_color=BORDER)
        shell.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.listbox = tk.Listbox(shell, bg=CARD_BG, fg=TEXT_PRIMARY, selectbackground="#374151", borderwidth=0, highlightthickness=0, font=("Arial", 17), activestyle="none")
        scroll = ctk.CTkScrollbar(shell, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 6), pady=8)
        self.listbox.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.refresh()
        self.after(100, lambda:maximize_window(self))

    def refresh(self):
        counts = self.store.dimension_counts(self.rows)[self.group_var.get()]
        self._data = sorted(counts.items(), key=lambda item:(-item[1], item[0].casefold()))
        self.listbox.delete(0, "end")
        self.listbox.insert("end", f"{'STORIES':>9}   {self.group_var.get().upper()}")
        for label, count in self._data:
            self.listbox.insert("end", f"{count:>9,}   {label}")
        self.total.configure(text=f"{len(self.rows):,} filtered stories • {len(self._data):,} {self.group_var.get().lower()} values")

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, title="Export content analytics", defaultextension=".csv", filetypes=[("CSV file", "*.csv")], initialfile=f"ldrs-{self.group_var.get().lower()}-analysis.csv")
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as target:
                writer = csv.writer(target)
                writer.writerow([self.group_var.get(), "Story count"])
                writer.writerows(self._data)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        messagebox.showinfo("Export complete", f"Saved {len(self._data):,} analytical rows.", parent=self)


class ContentIntelligenceWindow(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self._support = IntelligenceWindowSupport(self, master)
        self._support.install()
        self.title("Local Democracy Intelligence - NewsDesk Pro")
        self.geometry("1500x900")
        self.minsize(1180, 720)
        self.configure(fg_color=APP_BG)
        if master is not None:
            self.transient(master)
        self.store = ContentStore()
        self.rows, self.filtered, self._list_rows = [], [], []
        self.selected = None
        self._queue = Queue()
        self._working = False
        self._source_browsers = []
        self._image_service = ImageService(timeout=15)
        self._selected_image_asset = None
        self._detail_image = None
        self.search_var = ctk.StringVar(value="")
        self.area_var = ctk.StringVar(value=ALL)
        self.author_var = ctk.StringVar(value=ALL)
        self.type_var = ctk.StringVar(value=ALL)
        self.period_var = ctk.StringVar(value="All dates")
        settings = load_settings()
        self.scope_var = ctk.StringVar(value=str(settings.get("default_scope") or "Latest 500"))
        self._search_debounce = DebouncedAction(self._support, DEFAULT_SEARCH_DEBOUNCE_MS, self.apply_filters)
        self._build()
        self.refresh_database()
        self.after(100, lambda:maximize_window(self))

    def _build(self):
        self.grid_rowconfigure(2, weight=1); self.grid_columnconfigure(0, weight=1)
        self.header = NewsDeskHeader(
            self, module_title="Local Democracy Intelligence",
            subtitle="LDRS  •  Search  •  Analyse  •  Review  •  Social",
            primary_button_text="UPDATE CONTENT", primary_command=self.update_content,
            close_command=self._support.close,
            secondary_actions=(("API SETTINGS", self.open_api_settings), ("ANALYTICS", self.open_analytics), ("SOCIAL DESK", self.open_social_desk)),
        )
        self.header.grid(row=0, column=0, sticky="ew")
        filters = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0)
        filters.grid(row=1, column=0, sticky="ew")
        def group(label, first=False):
            frame=ctk.CTkFrame(filters,fg_color="transparent"); frame.pack(side="left",padx=((18 if first else 4),4),pady=(5,8))
            ctk.CTkLabel(frame,text=label,text_color=TEXT_MUTED,font=("Arial",10,"bold"),anchor="w").pack(fill="x",pady=(0,2)); return frame
        search_group=group("SEARCH",True)
        self.search=ctk.CTkEntry(search_group,textvariable=self.search_var,placeholder_text="Search LDRS content…",width=230); self.search.pack(); self.search.bind("<KeyRelease>",lambda _e:self._search_debounce.schedule())
        self.area=ctk.CTkOptionMenu(group("AREA / AUTHORITY"),variable=self.area_var,values=[ALL],width=175,command=lambda _v:self.apply_filters()); self.area.pack()
        self.author=ctk.CTkOptionMenu(group("AUTHOR"),variable=self.author_var,values=[ALL],width=160,command=lambda _v:self.apply_filters()); self.author.pack()
        self.kind=ctk.CTkOptionMenu(group("TYPE"),variable=self.type_var,values=[ALL,"Story","Advisory"],width=115,command=lambda _v:self.apply_filters()); self.kind.pack()
        self.period=ctk.CTkOptionMenu(group("PERIOD"),variable=self.period_var,values=["All dates","Last 7 days","Last 30 days","Last 90 days","This year"],width=135,command=lambda _v:self.apply_filters()); self.period.pack()
        self.scope=ctk.CTkOptionMenu(group("UPDATE SCOPE"),variable=self.scope_var,values=list(SCOPE_LIMITS),width=145); self.scope.pack()
        ctk.CTkButton(group(" "),text="RESET",width=88,fg_color=ACTION_BLUE,hover_color=ACTION_BLUE_HOVER,command=self.reset_filters).pack()
        self.count_label=ctk.CTkLabel(filters,text="0 stories",text_color=TEXT_SECONDARY,font=("Arial",12,"bold")); self.count_label.pack(side="right",padx=18)
        body=ctk.CTkFrame(self,fg_color=APP_BG); body.grid(row=2,column=0,sticky="nsew",padx=18,pady=16); body.grid_columnconfigure(0,weight=3); body.grid_columnconfigure(1,weight=2); body.grid_rowconfigure(0,weight=1)
        left=ctk.CTkFrame(body,fg_color=HEADER_BG,border_width=1,border_color=BORDER,corner_radius=12); left.grid(row=0,column=0,sticky="nsew",padx=(0,7))
        shell=ctk.CTkFrame(left,fg_color=CARD_BG,corner_radius=8); shell.pack(fill="both",expand=True,padx=10,pady=10)
        self.story_list=tk.Listbox(shell,bg=CARD_BG,fg=TEXT_PRIMARY,selectbackground="#374151",selectforeground=TEXT_PRIMARY,activestyle="none",borderwidth=0,highlightthickness=0,exportselection=False,font=("Arial",20))
        scroll=ctk.CTkScrollbar(shell,command=self.story_list.yview); self.story_list.configure(yscrollcommand=scroll.set); scroll.pack(side="right",fill="y",padx=(0,4),pady=6); self.story_list.pack(side="left",fill="both",expand=True,padx=(8,4),pady=8); self.story_list.bind("<<ListboxSelect>>",self._select_list_story)
        right=ctk.CTkFrame(body,fg_color=HEADER_BG,border_width=1,border_color=BORDER,corner_radius=12); right.grid(row=0,column=1,sticky="nsew",padx=(7,0)); self.detail=ctk.CTkScrollableFrame(right,fg_color="transparent"); self.detail.pack(fill="both",expand=True,padx=16,pady=14)
        self.status=ctk.CTkLabel(self,text="Local Democracy Intelligence ready",text_color=TEXT_MUTED,anchor="w",fg_color=HEADER_BG); self.status.grid(row=3,column=0,sticky="ew",ipadx=18,ipady=8)

    def refresh_database(self):
        self.rows=[row for row in self.store.list_stories() if _row_is_lincolnshire(row)]
        areas=sorted({area for row in self.rows for area in decode_list(row["authorities_json"])},key=str.casefold)
        authors=sorted({str(row["author"] or "").strip() for row in self.rows if str(row["author"] or "").strip()},key=str.casefold)
        types=sorted({str(row["content_type"] or "").strip() for row in self.rows if str(row["content_type"] or "").strip()},key=str.casefold)
        self.area.configure(values=[ALL,*areas]); self.author.configure(values=[ALL,*authors]); self.kind.configure(values=[ALL,*types] or [ALL,"Story","Advisory"])
        self.apply_filters()
        if self.selected is None: self._render_empty("Select a story to review its content.")
        summary = self.store.summary()
        latest = int(summary.get("latest_discovered") or 0)
        self.status.configure(text=f"Loaded {len(self.rows):,} stored Lincolnshire LDRS stories • latest refresh {latest:,} • {'API key configured' if has_api_key() else 'API key required'}")

    def reset_filters(self):
        self._search_debounce.cancel(); self.search_var.set(""); self.area_var.set(ALL); self.author_var.set(ALL); self.type_var.set(ALL); self.period_var.set("All dates"); self.apply_filters()

    def apply_filters(self):
        query=self.search_var.get().strip().casefold(); area=self.area_var.get(); author=self.author_var.get(); kind=self.type_var.get(); period=self.period_var.get(); now=datetime.now(timezone.utc)
        cutoff={"Last 7 days":now-timedelta(days=7),"Last 30 days":now-timedelta(days=30),"Last 90 days":now-timedelta(days=90)}.get(period)
        def visible(row):
            authorities=decode_list(row["authorities_json"]); hay=" ".join(str(row[key] or "") for key in ("title","slug","summary","body","author")) + " " + " ".join(authorities)
            created=_row_date(row)
            period_ok=(period=="All dates" or (period=="This year" and created and created.year==now.year) or (cutoff is not None and created and created>=cutoff))
            return (not query or query in hay.casefold()) and (area==ALL or area in authorities) and (author==ALL or row["author"]==author) and (kind==ALL or row["content_type"]==kind) and period_ok
        self.filtered=[row for row in self.rows if visible(row)]; self._render_list()
        latest = int(self.store.summary().get("latest_discovered") or 0)
        self.count_label.configure(text=f"{len(self.filtered):,}/{len(self.rows):,} stored • refresh {latest:,}")

    def _render_list(self):
        self.story_list.delete(0,"end"); self._list_rows=list(self.filtered)
        if not self.filtered: self.story_list.insert("end","No stories match the current filters."); self._list_rows=[]; return
        labels=[]
        for row in self.filtered:
            date=_display_date(row).split(" ",1)[0]; title=str(row["slug"] or row["title"]); author=str(row["author"] or "Unknown")
            labels.append(f"{date:<12} {title}  —  {author}")
        self.story_list.insert("end",*labels)
        # A Listbox can retain a horizontal offset after long headlines.  With
        # no horizontal scrollbar this made the leading day/month disappear.
        self.story_list.xview_moveto(0)

    def _select_list_story(self,_event=None):
        selected=self.story_list.curselection()
        if selected and int(selected[0])<len(self._list_rows): self.select(self._list_rows[int(selected[0])])

    def select(self,row):
        self.selected=row; self._render_detail(row)

    def _clear_detail(self):
        for child in self.detail.winfo_children(): child.destroy()
        self._detail_image=None; self._selected_image_asset=None

    def _render_empty(self,text):
        self._clear_detail(); ctk.CTkLabel(self.detail,text=text,text_color=TEXT_MUTED,wraplength=460).pack(pady=40)

    def _render_detail(self,row):
        self._clear_detail(); title=str(row["slug"] or row["title"]); ctk.CTkLabel(self.detail,text=title,font=("Arial",23,"bold"),text_color=TEXT_PRIMARY,anchor="w",justify="left",wraplength=560).pack(fill="x",pady=(2,8))
        from newsdesk.social.selection import social_workflow_status
        workflow_status = social_workflow_status(_story_from_row(row))
        if workflow_status:
            ctk.CTkLabel(self.detail,text=workflow_status,font=("Arial",12,"bold"),text_color="#22c55e" if workflow_status == "SENT TO METRICOOL" else "#60a5fa",anchor="w").pack(fill="x",pady=(0,10))
        authorities=", ".join(decode_list(row["authorities_json"])); categories=", ".join(decode_list(row["categories_json"])); fields=(("Created",_display_date(row)),("Author",row["author"]),("Area / authority",authorities),("Categories",categories),("Type",row["content_type"]),("Reviewer",row["reviewer_email"]))
        for label,value in fields:
            if not value: continue
            line=ctk.CTkFrame(self.detail,fg_color="transparent"); line.pack(fill="x",pady=5); ctk.CTkLabel(line,text=label,width=132,anchor="w",text_color=TEXT_MUTED).pack(side="left"); ctk.CTkLabel(line,text=str(value),anchor="w",justify="left",wraplength=400,text_color=TEXT_SECONDARY).pack(side="left",fill="x",expand=True)
        complete=bool(int(row["detail_complete"] or 0)); copy=_clean_article_copy(str(row["body"] or row["summary"] or "No story preview is available."), title)
        ctk.CTkLabel(self.detail,text="FULL CONTENT" if complete else "LISTING PREVIEW",font=("Arial",12,"bold"),text_color=TEXT_PRIMARY,anchor="w").pack(fill="x",pady=(18,6))
        if not complete:
            ctk.CTkLabel(self.detail,text="Download the full LDRS article before editorial review or social selection.",anchor="w",justify="left",wraplength=560,text_color=TEXT_MUTED).pack(fill="x",pady=(0,6))
            ctk.CTkButton(self.detail,text="DOWNLOAD FULL STORY",fg_color="#374151",command=self.download_selected_detail).pack(anchor="w",pady=(0,10))
        ctk.CTkLabel(self.detail,text=copy,anchor="w",justify="left",wraplength=560,text_color=TEXT_SECONDARY).pack(fill="x")
        image_url=str(row["image_url"] or "").strip()
        if image_url:
            asset=self._image_service.get(image_url,fallback_title=title); self._selected_image_asset=asset
            if asset.available and not asset.is_fallback:
                try:
                    picture=Image.open(asset.local_path); picture.thumbnail((560,310)); self._detail_image=ctk.CTkImage(light_image=picture,dark_image=picture,size=picture.size); ctk.CTkLabel(self.detail,text="",image=self._detail_image).pack(fill="x",pady=(18,6))
                    if row["image_caption"]: ctk.CTkLabel(self.detail,text=str(row["image_caption"]),wraplength=560,justify="left",text_color=TEXT_MUTED).pack(fill="x")
                except OSError: pass
        actions=ctk.CTkFrame(self.detail,fg_color="transparent"); actions.pack(fill="x",pady=(22,8))
        ctk.CTkButton(actions,text="OPEN SOURCE",width=118,fg_color=ACTION_BLUE,hover_color=ACTION_BLUE_HOVER,command=self.open_selected_source).pack(side="left",padx=(0,5))
        if complete:
            ctk.CTkButton(actions,text="COPY TO CLIPBOARD",width=140,fg_color=ACTION_BLUE,hover_color=ACTION_BLUE_HOVER,command=self.copy_selected).pack(side="left",padx=(0,5))
        ctk.CTkButton(actions,text="ADD TO SOCIALS",width=135,fg_color=ACTION_BLUE,hover_color=ACTION_BLUE_HOVER,command=self.add_to_social_desk).pack(side="left")

    def _api_key(self):
        try: return load_api_key()
        except CredentialError as exc: messagebox.showerror("API key",str(exc),parent=self); return ""

    def update_content(self):
        if self._working: return
        key=self._api_key()
        if not key: self.open_api_settings(); return
        scope=self.scope_var.get(); limit=SCOPE_LIMITS.get(scope,500); save_settings({"default_scope":scope}); self._working=True
        self.header.set_primary_button_text("UPDATING…"); self.header.set_primary_button_state("disabled")
        self.status.configure(text="Connecting securely to LDRS Content Explorer…")
        def worker():
            run_id=self.store.start_run(scope)
            try:
                with ContentExplorerCollector(key) as collector:
                    rows=collector.collect_listings(limit=limit,on_progress=lambda text:self._queue.put(("progress",text)))
                stored=self.store.upsert_many(rows); self.store.finish_run(run_id,discovered=len(rows),stored=stored,status="success"); self._queue.put(("done",len(rows),stored))
            except Exception as exc:
                self.store.finish_run(run_id,discovered=0,stored=0,status="failed",message=str(exc)); self._queue.put(("error",str(exc)))
        threading.Thread(target=worker,daemon=True,name="ldrs-content-update").start(); self.after(120,self._poll_queue)

    def _poll_queue(self):
        try:
            while True:
                item=self._queue.get_nowait(); kind=item[0]
                if kind=="progress": self.status.configure(text=item[1])
                elif kind=="done": self._working=False; self.header.set_primary_button_text("UPDATE CONTENT"); self.header.set_primary_button_state("normal"); self.refresh_database(); self.status.configure(text=f"UPDATE PASSED • {item[1]:,} Lincolnshire stories discovered • {item[2]:,} stored")
                elif kind=="detail": self._working=False; self.refresh_database(); row=self.store.get(item[1]); self.select(row); self.status.configure(text="Full LDRS story and media downloaded")
                elif kind=="detail_social":
                    self._working=False
                    self.refresh_database()
                    row=self.store.get(item[1])
                    self.select(row)
                    self.status.configure(text="Full LDRS story downloaded; adding it to Social Desk…")
                    # The detail refresh has already happened.  Stage this returned
                    # record directly so a weak/missing image credit cannot trigger
                    # the same download repeatedly and suppress the result dialog.
                    self.after(50, self._stage_selected_social_draft)
                elif kind=="tested": self._working=False; messagebox.showinfo("LDRS connection",f"Connection passed{(' for '+item[1]) if item[1] else ''}.",parent=self); self.status.configure(text="LDRS API-key connection passed")
                elif kind=="source_opened": self._working=False; self._source_browsers.append(item[1]); self.status.configure(text="Authenticated LDRS article opened in Chrome")
                elif kind=="error": self._working=False; self.header.set_primary_button_text("UPDATE CONTENT"); self.header.set_primary_button_state("normal"); self.status.configure(text="LDRS operation failed"); messagebox.showerror("Local Democracy Intelligence",item[1],parent=self)
        except Empty: pass
        if self._working: self.after(120,self._poll_queue)

    def download_selected_detail(self, then_add=False, then_social=False):
        if self.selected is None or self._working: return
        key=self._api_key()
        if not key: self.open_api_settings(); return
        article_id=str(self.selected["article_id"]); self._working=True; self.status.configure(text="Downloading full LDRS story and media…")
        def worker():
            try:
                with ContentExplorerCollector(key) as collector: detail=collector.fetch_detail(article_id)
                self.store.upsert_many([detail]); self._queue.put(("detail_social" if then_social else ("detail_add" if then_add else "detail"),article_id))
            except Exception as exc: self._queue.put(("error",str(exc)))
        threading.Thread(target=worker,daemon=True,name="ldrs-content-detail").start(); self.after(120,self._poll_queue)

    def copy_selected(self):
        if self.selected is None or not int(self.selected["detail_complete"] or 0): return
        story=_story_from_row(self.selected); asset=self._selected_image_asset
        if (asset is None or not asset.available or asset.is_fallback) and story.image_url:
            asset=self._image_service.get(story.image_url,fallback_title=story.title)
        image_path=getattr(asset,"local_path","") if asset is not None and asset.available and not asset.is_fallback else ""
        try:
            copy_rich_article(self,title=story.title,body=story.body or story.summary,image_path=image_path,caption=story.image_caption or story.image_credit,source_url=story.url,source_name=story.source)
        except (OSError,MemoryError) as exc: messagebox.showerror("Copy failed",str(exc),parent=self); return
        self.status.configure(text="Full LDRS article and image copied to the clipboard")

    def open_selected_source(self):
        if self.selected is None or self._working: return
        key=self._api_key()
        if not key: return
        article_id=str(self.selected["article_id"]); self._working=True; self.status.configure(text="Opening authenticated LDRS article…")
        def worker():
            try:
                collector=ContentExplorerCollector(key,headless=False); collector.open_article_visible(article_id); self._queue.put(("source_opened",collector))
            except Exception as exc: self._queue.put(("error",str(exc)))
        threading.Thread(target=worker,daemon=True,name="ldrs-open-source").start(); self.after(120,self._poll_queue)

    def open_api_settings(self):
        dialog=ctk.CTkToplevel(self); dialog.title("LDRS API settings"); dialog.geometry("650x340"); dialog.resizable(False,False); dialog.configure(fg_color=APP_BG); dialog.transient(self); dialog.grab_set(); ctk.CTkLabel(dialog,text="LDRS CONTENT EXPLORER",font=("Arial",20,"bold"),text_color=TEXT_PRIMARY).pack(anchor="w",padx=24,pady=(22,8)); ctk.CTkLabel(dialog,text="The API key is encrypted for this Windows account and is never committed to GitHub.",wraplength=590,justify="left",text_color=TEXT_SECONDARY).pack(anchor="w",padx=24,pady=(0,16)); entry=ctk.CTkEntry(dialog,show="•",placeholder_text="Enter or replace API key",width=590); entry.pack(padx=24,pady=8); state=ctk.CTkLabel(dialog,text="A key is already stored." if has_api_key() else "No API key is stored.",text_color=SUCCESS if has_api_key() else TEXT_MUTED); state.pack(anchor="w",padx=24,pady=(0,16))
        def save_and_test():
            value=entry.get().strip()
            try:
                if value: save_api_key(value)
                key=load_api_key()
                if not key: raise CredentialError("Enter the LDRS API key.")
            except CredentialError as exc: messagebox.showerror("API key",str(exc),parent=dialog); return
            dialog.destroy(); self._working=True; self.status.configure(text="Testing LDRS API-key access…")
            def worker():
                try:
                    with ContentExplorerCollector(key) as collector: result=collector.test_connection()
                    self._queue.put(("tested",str(result.get("account") or "")))
                except Exception as exc: self._queue.put(("error",str(exc)))
            threading.Thread(target=worker,daemon=True,name="ldrs-key-test").start(); self.after(120,self._poll_queue)
        buttons=ctk.CTkFrame(dialog,fg_color="transparent"); buttons.pack(fill="x",padx=24,pady=10); ctk.CTkButton(buttons,text="CANCEL",fg_color="#374151",command=dialog.destroy).pack(side="right"); ctk.CTkButton(buttons,text="SAVE + TEST",fg_color=ACCENT,command=save_and_test).pack(side="right",padx=(0,8))

    def open_analytics(self): ContentAnalyticsWindow(self,self.filtered)

    def add_to_social_desk(self):
        if getattr(self, "selected", None) is None:
            return
        if _needs_detail_refresh(self.selected):
            self.status.configure(text="Downloading the full LDRS story before adding it to socials…")
            self.download_selected_detail(then_social=True)
            return
        self._stage_selected_social_draft()

    def _stage_selected_social_draft(self):
        """Stage the selected LDRS story and always report the outcome."""

        if getattr(self, "selected", None) is None:
            messagebox.showwarning(
                "Add to Socials",
                "Select a Local Democracy story before adding it to Social Desk.",
                parent=self,
            )
            return
        from newsdesk.social.selection import add_story_to_social_desk
        try:
            story = _story_from_row(self.selected)
            draft = add_story_to_social_desk(self, story, module_key="content")
        except Exception as exc:
            self.status.configure(text="LDRS story could not be added to Social Desk")
            messagebox.showerror(
                "Add to Socials failed",
                f"The Local Democracy draft could not be created.\n\n{exc}",
                parent=self,
            )
            return
        if draft is not None:
            self.status.configure(text="LDRS story added to Social Desk")
            self._render_detail(self.selected)

    def open_social_desk(self):
        from modules.social_desk import open_social_desk
        return open_social_desk(self)


__all__ = ["ContentIntelligenceWindow", "get_content_dashboard_summary", "open_content"]
