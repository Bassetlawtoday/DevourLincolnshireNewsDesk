"""Events Intelligence workspace for NewsDesk Pro.

This module is intentionally isolated from the five established intelligence
collectors. It consumes the central NewsDesk UI/theme/newsletter services while
keeping event harvesting, storage and event-specific rules inside ``eventsdesk``.
"""
from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from queue import Empty, Queue
import json
import re
import sqlite3
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox
from urllib.parse import urlsplit

import customtkinter as ctk

from newsdesk.header import NewsDeskHeader
from newsdesk.image_preview_cache import IMAGE_PREVIEW_CACHE
from newsdesk.rich_clipboard import copy_rich_article
from newsdesk.services.image_service import ImageService
from newsdesk.story import Story
from newsdesk.theme import (
    ACTION_BLUE, ACTION_BLUE_HOVER, ACCENT, APP_BG, BORDER, BRAND_RED, BRAND_RED_HOVER, CARD_BG,
    HEADER_BG, SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from newsdesk.ui_support import (
    DEFAULT_SEARCH_DEBOUNCE_MS,
    DebouncedAction,
    IntelligenceWindowSupport,
    focus_existing_window,
    maximize_window,
)
from eventsdesk.source_catalog import SourceCatalog
from eventsdesk.source_scope import COUNTIES, enabled_sources
from eventsdesk.event_quality import has_event_signal, is_generic_non_event_title, is_news_url, repaired_event_title
from eventsdesk.enrichment import resolved_event_category

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVENTS_DATA_DIR = PROJECT_ROOT / "data" / "eventsdesk"
EVENTS_DATABASE = EVENTS_DATA_DIR / "eventsdesk.sqlite"
EVENTS_SUMMARY = EVENTS_DATA_DIR / "latest_harvest.json"
EVENTS_REJECTIONS = EVENTS_DATA_DIR / "rejected_events.json"
ALL = "All"
_active_window = None

_IMAGE_SOURCE_SUFFIXES = {
    ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp",
}


def _is_image_file_url(value: str | None) -> bool:
    """Return True when a URL points to an image rather than an event page."""
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        suffix = Path(urlsplit(raw).path).suffix.casefold()
    except ValueError:
        suffix = Path(raw.split("?", 1)[0].split("#", 1)[0]).suffix.casefold()
    return suffix in _IMAGE_SOURCE_SUFFIXES


def _normalise_web_url(value: str | None) -> str:
    raw = str(value or "").strip().rstrip(".,;:!?)\"]}")
    if not raw:
        return ""
    if raw.casefold().startswith("www."):
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _configured_source_url(source_name: str | None) -> str:
    wanted = str(source_name or "").strip().casefold()
    if not wanted:
        return ""
    try:
        config = next(
            (source for source in SourceCatalog.load_default().sources if source.name.casefold() == wanted),
            None,
        )
    except (OSError, ValueError, TypeError):
        config = None
    return _normalise_web_url(config.url if config else "")


def _row_provenance_url(row) -> str:
    """Select an event/ticket page, never a collected image-file address."""
    for field in ("event_url", "ticket_url"):
        value = _normalise_web_url(row[field])
        if value and not _is_image_file_url(value):
            return value
    try:
        return _configured_source_url(row["preferred_source"])
    except (KeyError, IndexError):
        return ""


_CONTENT_URL_RE = re.compile(
    r"(?i)(?:https?://|www\.)[^\s<>]+|(?<![@\w])(?:[a-z0-9-]+\.)+(?:co\.uk|org\.uk|gov\.uk|ac\.uk|com|org|net)(?:/[^\s<>]*)?"
)


def _content_links(text: str) -> list[tuple[int, int, str]]:
    links = []
    for match in _CONTENT_URL_RE.finditer(text or ""):
        display = match.group(0).rstrip(".,;:!?)\"]}")
        url = _normalise_web_url(display)
        if url:
            links.append((match.start(), match.start() + len(display), url))
    return links


def _connect():
    if not EVENTS_DATABASE.exists():
        return None
    connection = sqlite3.connect(EVENTS_DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def _event_rejection_key(row) -> str:
    """Stable editorial-rejection key, preferring the canonical source URL."""
    for field in ("event_url", "ticket_url"):
        try:
            value = str(row[field] or "").strip()
        except (KeyError, IndexError):
            value = ""
        if value:
            return f"url:{value.casefold()}"

    parts = []
    for field in ("title", "start", "preferred_source"):
        try:
            parts.append(str(row[field] or "").strip().casefold())
        except (KeyError, IndexError):
            parts.append("")
    return "fallback:" + "|".join(parts)


def _load_rejections() -> dict:
    if not EVENTS_REJECTIONS.exists():
        return {}
    try:
        payload = json.loads(EVENTS_REJECTIONS.read_text(encoding="utf-8-sig"))
        rows = payload.get("rejections", {})
        return rows if isinstance(rows, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_rejections(rejections: dict) -> None:
    EVENTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "rejections": rejections}
    EVENTS_REJECTIONS.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _row_is_rejected(row, rejections: dict | None = None) -> bool:
    rows = rejections if rejections is not None else _load_rejections()
    return _event_rejection_key(row) in rows


def _row_fails_quality_gate(row) -> bool:
    """Apply the same conservative false-positive rules to stored SQLite rows."""
    title = str(row["title"] or "").strip()
    if is_generic_non_event_title(title):
        return True

    # A card whose only clickable target is a JPG/PNG is catalogue artwork,
    # not sufficient legal provenance for a publishable event record.
    if not _row_provenance_url(row):
        event_url = str(row["event_url"] or "").strip()
        ticket_url = str(row["ticket_url"] or "").strip()
        if _is_image_file_url(event_url) or _is_image_file_url(ticket_url):
            return True

    event_url = str(row["event_url"] or "").strip()
    if is_news_url(event_url) and not has_event_signal(title):
        return True

    return False


def _format_event_datetime(value, *, include_time: bool = True) -> str:
    """Present stored ISO timestamps in UK day/month/year format."""
    if not value:
        return ""
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return raw
    date_text = parsed.strftime("%d/%m/%Y")
    if not include_time or (parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0):
        return date_text
    return f"{date_text} {parsed.strftime('%H:%M')}"


def _format_event_range(start_value, end_value, *, compact: bool = False) -> str:
    """Present an event's start/end as a clear UK date or date range."""
    if not start_value:
        return ""

    start_text = _format_event_datetime(start_value, include_time=not compact)
    if not end_value:
        return _format_event_datetime(start_value, include_time=not compact)

    try:
        start_dt = datetime.fromisoformat(str(start_value).strip().replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(end_value).strip().replace("Z", "+00:00"))
    except ValueError:
        end_text = _format_event_datetime(end_value, include_time=not compact)
        return f"{start_text} – {end_text}" if end_text else start_text

    if compact:
        start_date = start_dt.strftime("%d/%m/%Y")
        end_date = end_dt.strftime("%d/%m/%Y")
        if start_dt.date() == end_dt.date():
            return start_date
        return f"{start_date} – {end_date}"

    # Same-day timed event: avoid repeating the date.
    if start_dt.date() == end_dt.date():
        date_text = start_dt.strftime("%d/%m/%Y")
        start_has_time = any((start_dt.hour, start_dt.minute, start_dt.second))
        end_has_time = any((end_dt.hour, end_dt.minute, end_dt.second))
        if start_has_time or end_has_time:
            return f"{date_text} {start_dt.strftime('%H:%M')} – {end_dt.strftime('%H:%M')}"
        return date_text

    return (
        f"{_format_event_datetime(start_value)} – "
        f"{_format_event_datetime(end_value)}"
    )


def get_event_dashboard_summary() -> dict:
    """Return a lightweight aggregate without loading every event at startup."""
    connection = _connect()
    if connection is None:
        return {"count": 0, "status": "Not yet collected", "updated": "Never"}
    try:
        sources = enabled_sources(SourceCatalog.load_default(), EVENTS_DATA_DIR)
        names = sorted(source.name for source in sources)
        if not names:
            return {"count": 0, "status": "No EventsDesk feeds enabled", "updated": "Never"}
        placeholders = ",".join("?" for _ in names)
        row = connection.execute(
            "SELECT COUNT(DISTINCT e.id) AS event_count, MAX(e.last_seen_at) AS updated "
            "FROM events e WHERE e.active=1 "
            "AND e.lifecycle_state IN ('scheduled','postponed') "
            "AND EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id=e.id "
            f"AND s.source IN ({placeholders}) AND s.missing_since IS NULL)",
            names,
        ).fetchone()
        count = int(row["event_count"] or 0) if row is not None else 0
        updated = str(row["updated"] or "Never") if row is not None else "Never"
        return {
            "count": count,
            "status": f"{len(names)} EventsDesk feeds enabled",
            "updated": updated,
        }
    except sqlite3.Error:
        return {"count": 0, "status": "Event database needs refresh", "updated": "Unknown"}
    finally:
        connection.close()


def _row_display_title(row) -> str:
    return repaired_event_title(row["title"], row["preferred_source"], row["event_url"])


class _EventDescriptionParser(HTMLParser):
    """Small dependency-free HTML-to-text parser for collected descriptions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._ignored_depth = 0
        self._links = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag.casefold() in {"script", "style"}:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag.casefold() in {
            "br", "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"
        }:
            self.parts.append("\n\n")
        if not self._ignored_depth and tag.casefold() == "a":
            href = next((value for name, value in attrs if name.casefold() == "href"), "")
            self._links.append(str(href or "").strip())

    def handle_endtag(self, tag) -> None:
        if tag.casefold() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag.casefold() in {
            "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"
        }:
            self.parts.append("\n\n")
        elif not self._ignored_depth:
            self.parts.append(" ")
        if not self._ignored_depth and tag.casefold() == "a" and self._links:
            href = self._links.pop()
            if href.startswith(("http://", "https://", "mailto:")):
                self.parts.append(f" {href} ")

    def handle_data(self, data) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def _clean_event_description(value) -> str:
    """Convert source HTML into readable text while preserving its wording."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = re.sub(
        r"\[embed(?:\s[^\]]*)?\].*?\[/embed\]",
        " ",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    parser = _EventDescriptionParser()
    try:
        parser.feed(raw)
        parser.close()
    except (ValueError, TypeError):
        return " ".join(raw.split())
    text = re.sub(r"\\n", " ", "".join(parser.parts))
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", text)]
    text = "\n\n".join(part for part in paragraphs if part).strip()
    truncated = re.search(r"\s*(?:\[…\]|\[\.\.\.\])\s*$", text)
    if truncated:
        complete = text[:truncated.start()].rstrip()
        sentence_end = max(complete.rfind("."), complete.rfind("!"), complete.rfind("?"))
        if sentence_end >= 0:
            complete = complete[:sentence_end + 1]
        text = complete
    return text


def _row_display_category(row) -> str:
    return str(
        resolved_event_category(
            row["category"], row["title"], row["description"], row["venue"]
        )
        or row["category"]
        or ""
    ).strip()


def _row_is_cinema_event(row) -> bool:
    return _row_display_category(row).casefold() in {
        "film", "cinema", "movie", "event cinema"
    }


def _event_newsletter_copy(row) -> str:
    """Build accurate, editor-ready event copy without inventing details."""
    paragraphs = []

    description = _clean_event_description(row["description"])
    if description:
        paragraphs.append(description)

    details = []
    date_text = _format_event_range(row["start"], row["end"])
    if date_text:
        details.append(f"When: {date_text}")

    location = ", ".join(
        str(row[field]).strip()
        for field in ("venue", "address", "town", "county", "postcode")
        if row[field] and str(row[field]).strip()
    )
    if location:
        details.append(f"Where: {location}")

    price = _format_event_price(row["price_text"])
    if price:
        details.append(f"Price: {price}")

    age = " ".join(str(row["age_restriction"] or "").split())
    if age:
        details.append(f"Age information: {age}")

    if details:
        paragraphs.extend(details)

    return "\n\n".join(paragraphs)


def _format_event_price(value) -> str:
    """Add the pound symbol to plain numeric UK prices without guessing text."""
    price = " ".join(str(value or "").split())
    if not price:
        return ""
    if re.fullmatch(r"\d+(?:\.\d{1,2})?", price):
        return f"£{price}"
    return price


def _event_story(row) -> Story:
    start = str(row["start"] or "")
    location = ", ".join(
        str(row[field]).strip()
        for field in ("venue", "address", "town", "county", "postcode")
        if row[field] and str(row[field]).strip()
    )
    description = _clean_event_description(row["description"])
    newsletter_copy = _event_newsletter_copy(row)
    return Story(
        story_id=f"events:{row['id']}",
        title=_row_display_title(row),
        summary=newsletter_copy,
        body=description,
        source=str(row["preferred_source"] or "EventsDesk").strip(),
        url=_row_provenance_url(row),
        published=start,
        location=location,
        category=str(row["category"] or "Events").strip(),
        image_url=str(row["image_url"] or "").strip(),
        image_credit=str(row["preferred_source"] or "").strip(),
        image_alt_text=_row_display_title(row),
        extras={
            "event_end": str(row["end"] or "").strip(),
            "event_price": str(row["price_text"] or "").strip(),
            "event_age_restriction": str(row["age_restriction"] or "").strip(),
            "event_ticket_url": str(row["ticket_url"] or "").strip(),
        },
    )


def open_events(master=None):
    global _active_window
    if focus_existing_window(_active_window):
        return _active_window
    _active_window = EventsIntelligenceWindow(master)
    return _active_window


class EventsIntelligenceWindow(ctk.CTkToplevel):
    """Search, review, refresh and newsletter-select current events."""
    def __init__(self, master=None):
        super().__init__(master)
        self._support = IntelligenceWindowSupport(self, master)
        self._support.install()
        self.title("Events Intelligence - Devour Lincolnshire NewsDesk")
        self.geometry("1500x900")
        self.minsize(1180, 720)
        self.configure(fg_color=APP_BG)
        if master is not None:
            self.transient(master)
        self.rows = []
        self.filtered = []
        self._list_rows = []
        self.selected = None
        self._harvest_queue = Queue()
        self._image_queue = Queue()
        self._image_service = ImageService(timeout=12)
        self._image_request = 0
        self._image_loading = False
        self._detail_image = None
        self._selected_image_asset = None
        self._harvesting = False
        self._harvest_started_at = None
        self._harvest_pulse = 0
        self._harvest_progress = None
        self._search_debounce = DebouncedAction(
            self._support,
            DEFAULT_SEARCH_DEBOUNCE_MS,
            self.apply_filters,
        )
        self.search_var = ctk.StringVar(value="")
        self.town_var = ctk.StringVar(value=ALL)
        self.county_var = ctk.StringVar(value=ALL)
        self.category_var = ctk.StringVar(value=ALL)
        self.quality_var = ctk.StringVar(value=ALL)
        self.scope_var = ctk.StringVar(value="All enabled sources")
        self._build()
        self.refresh_database()
        self.after(100, lambda: maximize_window(self))

    def _build(self):
        self.grid_rowconfigure(2, weight=1); self.grid_columnconfigure(0, weight=1)
        self.header = NewsDeskHeader(
            self,
            module_title="Events Intelligence",
            subtitle="Collect  •  Search  •  Review  •  Social",
            primary_button_text="UPDATE EVENTS",
            primary_command=self.harvest,
            close_command=self._support.close,
            secondary_actions=(("SOURCES", self.open_source_manager), ("SOCIAL DESK", self.open_social_desk)),
        )
        self.header.grid(row=0,column=0,sticky="ew")
        filters=ctk.CTkFrame(self,fg_color=HEADER_BG,corner_radius=0)
        filters.grid(row=1,column=0,sticky="ew",padx=0,pady=0)
        def filter_group(label, *, first=False):
            group = ctk.CTkFrame(filters, fg_color="transparent")
            group.pack(side="left", padx=((20 if first else 4), 4), pady=(5, 8))
            ctk.CTkLabel(group, text=label, text_color=TEXT_MUTED,
                         font=("Arial", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 2))
            return group

        search_group = filter_group("SEARCH", first=True)
        self.search=ctk.CTkEntry(search_group,textvariable=self.search_var,placeholder_text="Search events...",width=250)
        self.search.pack()
        self.search.bind("<KeyRelease>",lambda _e:self._search_debounce.schedule())
        self.town=ctk.CTkOptionMenu(filter_group("TOWN"),variable=self.town_var,values=[ALL],width=170,command=lambda _v:self.apply_filters())
        self.town.pack()
        self.county=ctk.CTkOptionMenu(filter_group("COUNTY"),variable=self.county_var,values=[ALL],width=170,command=lambda _v:self.apply_filters())
        self.county.pack()
        self.category=ctk.CTkOptionMenu(filter_group("CATEGORY"),variable=self.category_var,values=[ALL],width=180,command=lambda _v:self.apply_filters())
        self.category.pack()
        self.quality=ctk.CTkOptionMenu(filter_group("QUALITY"),variable=self.quality_var,values=[ALL,"complete","usable","limited","review"],width=130,command=lambda _v:self.apply_filters())
        self.quality.pack()
        self.scope_menu=ctk.CTkOptionMenu(
            filter_group("UPDATE SCOPE"), variable=self.scope_var, values=["All enabled sources", *COUNTIES], width=180
        )
        self.scope_menu.pack()
        reset_group = filter_group(" ")
        ctk.CTkButton(
            reset_group,text="RESET",width=90,fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,command=self.reset_filters,
        ).pack()
        self.count_label=ctk.CTkLabel(filters,text="0 events",text_color=TEXT_SECONDARY,font=("Arial",12,"bold"))
        self.count_label.pack(side="right",padx=20)

        body=ctk.CTkFrame(self,fg_color=APP_BG); body.grid(row=2,column=0,sticky="nsew",padx=18,pady=16)
        body.grid_columnconfigure(0,weight=3); body.grid_columnconfigure(1,weight=2); body.grid_rowconfigure(0,weight=1)
        left=ctk.CTkFrame(body,fg_color=HEADER_BG,border_width=1,border_color=BORDER,corner_radius=12)
        left.grid(row=0,column=0,sticky="nsew",padx=(0,7));
        list_shell=ctk.CTkFrame(left,fg_color=CARD_BG,corner_radius=8)
        list_shell.pack(fill="both",expand=True,padx=10,pady=10)
        self.event_list=tk.Listbox(
            list_shell,
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            selectbackground="#374151",
            selectforeground=TEXT_PRIMARY,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            exportselection=False,
            font=("Arial",24),
        )
        list_scroll=ctk.CTkScrollbar(list_shell,command=self.event_list.yview)
        self.event_list.configure(yscrollcommand=list_scroll.set)
        list_scroll.pack(side="right",fill="y",padx=(0,4),pady=6)
        self.event_list.pack(side="left",fill="both",expand=True,padx=(8,4),pady=8)
        self.event_list.bind("<<ListboxSelect>>",self._select_list_event)
        right=ctk.CTkFrame(body,fg_color=HEADER_BG,border_width=1,border_color=BORDER,corner_radius=12)
        right.grid(row=0,column=1,sticky="nsew",padx=(7,0))
        self.detail=ctk.CTkScrollableFrame(right,fg_color="transparent")
        self.detail.pack(fill="both",expand=True,padx=16,pady=14)
        self.status=ctk.CTkLabel(self,text="Events Intelligence ready",text_color=TEXT_MUTED,anchor="w",fg_color=HEADER_BG)
        self.status.grid(row=3,column=0,sticky="ew",ipadx=18,ipady=8)

    def _enabled_source_rows(self, county=None):
        return enabled_sources(SourceCatalog.load_default(), EVENTS_DATA_DIR, county)

    def _enabled_source_names(self):
        return {source.name for source in self._enabled_source_rows()}

    def open_source_manager(self):
        from modules.events_sources import EventSourceManager
        EventSourceManager(self, EVENTS_DATA_DIR, on_saved=self._source_preferences_saved)

    def _source_preferences_saved(self):
        self.refresh_database()
        self.status.configure(text="EventsDesk source preferences saved.")

    def refresh_database(self):
        connection=_connect()
        if connection is None:
            self.rows=[]; self.filtered=[]; self._render_list(); self._render_empty("No event database yet. Select UPDATE EVENTS to run the first collection.")
            return
        try:
            enabled_names = sorted(self._enabled_source_names())
            if not enabled_names:
                self.rows = []
            else:
                placeholders = ",".join("?" for _ in enabled_names)
                db_rows=connection.execute(
                    "SELECT DISTINCT e.* FROM events e "
                    "WHERE e.active=1 AND e.lifecycle_state IN ('scheduled','postponed') "
                    "AND EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id=e.id "
                    f"AND s.source IN ({placeholders}) AND s.missing_since IS NULL) "
                    "ORDER BY CASE WHEN e.start IS NULL THEN 1 ELSE 0 END, e.start, e.title",
                    enabled_names,
                ).fetchall()
                rejections = _load_rejections()
                self.rows = [
                    row for row in db_rows
                    if not _row_is_rejected(row, rejections)
                    and not _row_fails_quality_gate(row)
                    and not _row_is_cinema_event(row)
                ]
        finally:
            connection.close()
        self._set_filter_values(); self.apply_filters()
        if self.selected is None:
            self._render_empty("Select an event to view its details.")
        self.status.configure(text=f"Loaded {len(self.rows):,} current Greater Lincolnshire events")

    def _set_filter_values(self):
        def values(field): return [ALL,*sorted({str(r[field]).strip() for r in self.rows if r[field]},key=str.casefold)]
        categories=[ALL,*sorted({_row_display_category(r) for r in self.rows if _row_display_category(r)},key=str.casefold)]
        self.town.configure(values=values("town")); self.county.configure(values=values("county")); self.category.configure(values=categories)

    def reset_filters(self):
        self._search_debounce.cancel()
        self.search_var.set(""); self.town_var.set(ALL); self.county_var.set(ALL); self.category_var.set(ALL); self.quality_var.set(ALL); self.apply_filters()

    def apply_filters(self):
        q=self.search_var.get().strip().casefold(); town=self.town_var.get(); county=self.county_var.get(); category=self.category_var.get(); quality=self.quality_var.get()
        def ok(r):
            hay=" ".join(str(r[k] or "") for k in ("title","venue","town","county","category","description","preferred_source")).casefold()
            return (not q or q in hay) and (town==ALL or r["town"]==town) and (county==ALL or r["county"]==county) and (category==ALL or _row_display_category(r)==category) and (quality==ALL or r["quality_status"]==quality)
        self.filtered=[r for r in self.rows if ok(r)]
        self._render_list(); self.count_label.configure(text=f"{len(self.filtered):,}/{len(self.rows):,} events")

    def _render_list(self):
        self.event_list.delete(0,"end")
        self._list_rows=list(self.filtered)
        if not self.filtered:
            self.event_list.insert("end","No events match the current filters.")
            self._list_rows=[]
            return
        labels=[]
        for row in self.filtered:
            start=str(row["start"] or "")
            date=_format_event_range(row["start"], row["end"], compact=True) if start else "Date TBC"
            label=_row_display_title(row) + (f"  —  {row['town']}" if row['town'] else "")
            labels.append(f"{date:<25} {label}")
        self.event_list.insert("end",*labels)

    def _select_list_event(self,_event=None):
        selection=self.event_list.curselection()
        if not selection: return
        index=int(selection[0])
        if 0 <= index < len(self._list_rows):
            self.select(self._list_rows[index])

    def select(self,row): self.selected=row; self._render_detail(row)

    def _render_empty(self,text):
        self._image_request += 1
        self._image_loading = False
        self._detail_image = None
        self._selected_image_asset = None
        for child in self.detail.winfo_children(): child.destroy()
        ctk.CTkLabel(self.detail,text=text,text_color=TEXT_MUTED,wraplength=500,justify="left").pack(anchor="w",pady=20)

    def _render_detail(self,row):
        self._image_request += 1
        request_id = self._image_request
        self._image_loading = False
        self._detail_image = None
        self._selected_image_asset = None
        for child in self.detail.winfo_children(): child.destroy()
        ctk.CTkLabel(self.detail,text=_row_display_title(row),font=("Arial",22,"bold"),text_color=TEXT_PRIMARY,wraplength=520,justify="left",anchor="w").pack(fill="x",pady=(4,12))
        fields=(("Date / time",_format_event_range(row["start"], row["end"])),("Venue",row["venue"]),("Town",row["town"]),("County",row["county"]),("Category",_row_display_category(row)),("Price",_format_event_price(row["price_text"])),("Age",row["age_restriction"]),("Source",row["preferred_source"]),("Quality",f"{row['quality_status'] or 'unknown'} ({row['quality_score'] or 0}/100)"))
        for label,value in fields:
            if not value: continue
            line=ctk.CTkFrame(self.detail,fg_color="transparent"); line.pack(fill="x",pady=2)
            ctk.CTkLabel(line,text=label,width=110,anchor="w",text_color=TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(line,text=str(value),anchor="w",text_color=TEXT_SECONDARY,wraplength=390,justify="left").pack(side="left",fill="x",expand=True)
        description = _clean_event_description(row["description"])
        if description:
            ctk.CTkLabel(self.detail,text="DESCRIPTION",font=("Arial",12,"bold"),text_color=TEXT_PRIMARY,anchor="w").pack(fill="x",pady=(14,4))
            self._render_linkable_description(description)
        image_url = str(row["image_url"] or "").strip()
        ctk.CTkLabel(self.detail,text="SOURCE IMAGE",font=("Arial",12,"bold"),text_color=TEXT_PRIMARY,anchor="w").pack(fill="x",pady=(16,4))
        self._image_status_label = ctk.CTkLabel(
            self.detail,
            text="Loading image…" if image_url else "No image was collected for this event.",
            text_color=TEXT_MUTED, wraplength=520, justify="left", anchor="w",
        )
        self._image_status_label.pack(fill="x")
        self._image_preview_label = ctk.CTkLabel(self.detail, text="")
        self._image_preview_label.pack(fill="x", pady=(6,0))
        if image_url:
            self._image_loading = True
            threading.Thread(
                target=self._load_image_preview,
                args=(request_id, image_url, _row_display_title(row)),
                daemon=True,
            ).start()
            self._support.call_later(100, self._poll_image_preview)
        actions=ctk.CTkFrame(self.detail,fg_color="transparent"); actions.pack(fill="x",pady=(18,4))
        url=_row_provenance_url(row)
        ctk.CTkButton(actions,text="OPEN SOURCE",width=118,fg_color=ACTION_BLUE,hover_color=ACTION_BLUE_HOVER,state="normal" if url else "disabled",command=lambda:webbrowser.open(url) if url else None).pack(side="left",padx=(0,5))
        ctk.CTkButton(actions,text="COPY TO CLIPBOARD",width=140,fg_color=ACTION_BLUE,hover_color=ACTION_BLUE_HOVER,command=self.copy_selected_event).pack(side="left",padx=(0,5))
        second_actions=ctk.CTkFrame(self.detail,fg_color="transparent"); second_actions.pack(fill="x",pady=(0,6))
        ctk.CTkButton(second_actions,text="ADD TO SOCIALS",width=145,fg_color=ACTION_BLUE,hover_color=ACTION_BLUE_HOVER,command=self.add_to_social_desk).pack(side="left",padx=(0,5))
        ctk.CTkButton(second_actions,text="NOT AN EVENT",width=145,fg_color=BRAND_RED,hover_color=BRAND_RED_HOVER,command=self.reject_selected_event).pack(side="left")

    def _render_linkable_description(self, description: str) -> None:
        lines = max(3, min(22, description.count("\n") + (len(description) // 82) + 1))
        widget = tk.Text(
            self.detail, height=lines, wrap="word", bg=CARD_BG, fg=TEXT_SECONDARY,
            insertbackground=TEXT_PRIMARY, relief="flat", borderwidth=0,
            highlightthickness=0, font=("Arial", 12), cursor="arrow",
        )
        widget.insert("1.0", description)
        widget.tag_configure("event_link", foreground="#60A5FA", underline=True)
        for index, (start, end, url) in enumerate(_content_links(description)):
            tag = f"event_link_{index}"
            widget.tag_add("event_link", f"1.0+{start}c", f"1.0+{end}c")
            widget.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")
            widget.tag_bind(tag, "<Button-1>", lambda _event, target=url: webbrowser.open(target))
            widget.tag_bind(tag, "<Enter>", lambda _event, view=widget: view.configure(cursor="hand2"))
            widget.tag_bind(tag, "<Leave>", lambda _event, view=widget: view.configure(cursor="arrow"))
        widget.configure(state="disabled")
        widget.pack(fill="x")

    def _load_image_preview(self, request_id, image_url, title):
        asset = self._image_service.get(image_url, fallback_title=title)
        preview = None
        if asset.available and not asset.is_fallback:
            preview = IMAGE_PREVIEW_CACHE.get(asset.local_path, (520, 280))
        self._image_queue.put((request_id, asset, preview))

    def _poll_image_preview(self):
        try:
            request_id, asset, preview = self._image_queue.get_nowait()
        except Empty:
            if self._image_loading:
                self._support.call_later(100, self._poll_image_preview)
            return
        if request_id != self._image_request:
            if self._image_loading:
                self._support.call_later(100, self._poll_image_preview)
            return
        self._image_loading = False
        if preview is None:
            self._image_status_label.configure(text="Image unavailable. It will remain excluded from social use.")
            return
        self._selected_image_asset = asset
        self._detail_image = ctk.CTkImage(
            light_image=preview, dark_image=preview, size=preview.size
        )
        self._image_preview_label.configure(image=self._detail_image)
        self._image_status_label.configure(
            text="Image collected from the event source. Rights approval is reviewed before social use."
        )

    def reject_selected_event(self):
        if self.selected is None:
            return
        title = _row_display_title(self.selected)
        if not messagebox.askyesno(
            "Not an event",
            f"Hide '{title}' from EventsDesk and remember this rejection for future refreshes?",
            parent=self,
        ):
            return

        rejections = _load_rejections()
        key = _event_rejection_key(self.selected)
        rejections[key] = {
            "title": title,
            "start": str(self.selected["start"] or ""),
            "source": str(self.selected["preferred_source"] or ""),
            "event_url": str(self.selected["event_url"] or ""),
            "ticket_url": str(self.selected["ticket_url"] or ""),
            "rejected_at": datetime.now().astimezone().isoformat(),
            "reason": "editorial_not_an_event",
        }
        _save_rejections(rejections)

        self.selected = None
        self.refresh_database()
        self._render_empty("Select an event to view its details.")
        self.status.configure(
            text=f"Rejected as not an event — {title}. It will remain hidden after future refreshes."
        )

    def copy_selected_event(self):
        if self.selected is None: return
        story=_event_story(self.selected); asset=self._selected_image_asset
        if (asset is None or not asset.available or asset.is_fallback) and story.image_url:
            asset=self._image_service.get(story.image_url,fallback_title=story.title)
        image_path=getattr(asset,"local_path","") if asset is not None and asset.available and not asset.is_fallback else ""
        caption=str(self.selected["preferred_source"] or "").strip()
        try:
            copy_rich_article(self,title=story.title,body=story.summary,image_path=image_path,caption=caption,source_url=story.url,source_name=story.source)
        except (OSError,MemoryError) as exc: messagebox.showerror("Copy failed",str(exc),parent=self); return
        self.status.configure(text="Complete event copy and image copied to the clipboard")


    def add_to_social_desk(self):
        if getattr(self, "selected", None) is None:
            return
        from newsdesk.social.selection import add_story_to_social_desk
        row = self.selected
        story = _event_story(row)
        story.body = story.summary
        add_story_to_social_desk(self, story, module_key="events")

    def open_social_desk(self):
        from modules.social_desk import open_social_desk
        return open_social_desk(self)

    def harvest(self):
        if self._harvesting:
            return

        scope = self.scope_var.get()
        selected = self._enabled_source_rows(None if scope == "All enabled sources" else scope)
        if not selected:
            messagebox.showwarning(
                "Events update", f"No enabled EventsDesk feeds are available for {scope}.", parent=self
            )
            return

        self._harvesting = True
        self._harvest_started_at = time.monotonic()
        self._harvest_progress = {"index": 0, "total": len(selected), "source": "Starting"}
        self.header.set_primary_button_text("UPDATING EVENTS")
        self.header.set_primary_button_state("disabled")
        self.scope_menu.configure(state="disabled")
        self.status.configure(text=f"Updating {len(selected)} enabled feeds — {scope} — starting...")
        if self.selected is None:
            self._render_empty("Updating events now. You can continue to use the event list while collection runs.")

        EVENTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
        source_ids = [source.id for source in selected]

        def progress(info):
            self._harvest_queue.put(("progress", info))

        def worker():
            try:
                from eventsdesk.harvest_engine import MidlandsHarvestEngine
                result = MidlandsHarvestEngine().harvest(
                    database=str(EVENTS_DATABASE),
                    output=str(EVENTS_SUMMARY),
                    source_ids=source_ids,
                    skip_network_preflight=False,
                    progress_callback=progress,
                )
                self._harvest_queue.put(("done", True, result))
            except Exception as exc:
                self._harvest_queue.put(("done", False, exc))

        threading.Thread(target=worker, name="eventsdesk-harvest", daemon=True).start()
        self.after(250, self._poll_harvest)

    def _poll_harvest(self):
        try:
            while True:
                message = self._harvest_queue.get_nowait()
                if message[0] == "progress":
                    self._harvest_progress = message[1]
                    continue

                _, ok, payload = message
                self._harvesting = False
                self._harvest_started_at = None
                self.header.set_primary_button_text("UPDATE EVENTS")
                self.header.set_primary_button_state("normal")
                self.scope_menu.configure(state="normal")

                if ok:
                    self.refresh_database()
                    checked = payload.get("selected_sources", 0)
                    successful = payload.get("successful_sources", 0)
                    zero_yield = payload.get("zero_yield_sources", 0)
                    blocked = payload.get("access_blocked_sources", 0)
                    failed = payload.get("failed_sources", 0)
                    self.status.configure(
                        text=(f"Update complete — {checked} feeds checked • {successful} producing • "
                              f"{zero_yield} zero-yield • {blocked} blocked • {failed} failed")
                    )
                else:
                    self.status.configure(text=f"Event update failed: {payload}")
                    messagebox.showerror("Events update failed", str(payload), parent=self)
                return
        except Empty:
            pass

        if self._harvesting:
            elapsed = int(time.monotonic() - self._harvest_started_at) if self._harvest_started_at else 0
            progress = self._harvest_progress or {}
            index = progress.get("index", 0)
            total = progress.get("total", 0)
            source = progress.get("source", "Starting")
            if index and total:
                self.status.configure(text=f"Updating feed {index} of {total} — {source} — {elapsed}s elapsed")
            else:
                self.status.configure(text=f"Updating events — {elapsed}s elapsed")
            self.after(500, self._poll_harvest)
