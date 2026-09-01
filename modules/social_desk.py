"""Social Desk: safe local staging with optional Metricool draft delivery."""

from __future__ import annotations

from datetime import datetime, timedelta
import threading
from tkinter import messagebox

import customtkinter as ctk

from newsdesk.social.metricool import MetricoolClient, MetricoolError
from newsdesk.social.store import SocialDraft, SocialDraftStore, SocialSettingsStore
from newsdesk.social.text import clean_social_text, compose_metricool_text
from newsdesk.theme import (
    ACTION_BLUE, ACTION_BLUE_HOVER, APP_BG, BORDER, BRAND_RED, BRAND_RED_HOVER,
    CARD_BG, HEADER_BG, SUCCESS, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from newsdesk.ui_support import present_window_foreground


NETWORKS = (
    ("Facebook", "facebook"), ("Instagram", "instagram"),
    ("X", "twitter"), ("LinkedIn", "linkedin"),
    ("Threads", "threads"), ("Bluesky", "bluesky"),
)


class SocialDesk(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Social Desk — NewsDesk Pro")
        self.configure(fg_color=APP_BG)
        self.minsize(1150, 720)
        self.store = SocialDraftStore()
        self.settings_store = SocialSettingsStore()
        self.drafts = self.store.load()
        self.current: SocialDraft | None = None
        self.network_vars: dict[str, ctk.BooleanVar] = {}
        self.draft_search_var = ctk.StringVar()
        self.draft_filter_var = ctk.StringVar(value="ALL")
        self._build()
        self._refresh_list()
        self.after_idle(lambda: present_window_foreground(self, temporary_topmost=True, maximized=True))

    def _build(self):
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=105)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="SOCIAL DESK", font=("Arial", 28, "bold"), text_color=TEXT_PRIMARY).pack(side="left", padx=28)
        buttons = ctk.CTkFrame(header, fg_color="transparent")
        buttons.pack(side="right", padx=24)
        ctk.CTkButton(buttons, text="METRICOOL SETTINGS", width=155, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self._settings).pack(side="left", padx=5)
        ctk.CTkButton(buttons, text="CLOSE", width=100, fg_color="#475569", command=self.destroy).pack(side="left", padx=5)

        status = ctk.CTkFrame(self, fg_color="transparent")
        status.pack(fill="x", padx=28, pady=(12, 8))
        self.connection_label = ctk.CTkLabel(status, text="", text_color=TEXT_MUTED, anchor="w")
        self.connection_label.pack(fill="x")
        ctk.CTkLabel(status, text="SAFE MODE — Metricool receives drafts only; Social Desk never publishes automatically.", text_color=SUCCESS, anchor="w").pack(fill="x", pady=(3, 0))
        self._show_connection_state()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 22))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=HEADER_BG, border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        toolbar = ctk.CTkFrame(left, fg_color="transparent")
        toolbar.pack(fill="x", padx=12, pady=12)
        ctk.CTkButton(toolbar, text="NEW BLANK POST", width=140, command=self._new).pack(side="left")
        ctk.CTkLabel(
            left,
            text="Create a blank post here, or add newsroom content directly from its intelligence module.",
            text_color=TEXT_MUTED,
            wraplength=345,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 9))
        list_controls = ctk.CTkFrame(left, fg_color="transparent")
        list_controls.pack(fill="x", padx=12, pady=(0, 9))
        search = ctk.CTkEntry(
            list_controls,
            textvariable=self.draft_search_var,
            placeholder_text="Search drafts",
            width=190,
        )
        search.pack(side="left", fill="x", expand=True, padx=(0, 6))
        search.bind("<KeyRelease>", lambda _event: self._refresh_list())
        ctk.CTkOptionMenu(
            list_controls,
            values=["ALL", "LOCAL DEMOCRACY", "EVENTS", "PLANNING", "POLICE", "FIRE", "SPORT", "COUNCIL", "BLANK"],
            variable=self.draft_filter_var,
            command=lambda _value: self._refresh_list(),
            width=145,
        ).pack(side="left")
        self.list_frame = ctk.CTkScrollableFrame(left, fg_color=CARD_BG)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        right = ctk.CTkFrame(body, fg_color=HEADER_BG, border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        form = ctk.CTkScrollableFrame(right, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=(14, 8))
        self.title_entry = self._entry(form, "Working title (not sent to social networks)")
        ctk.CTkLabel(form, text="Post text", text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", pady=(10, 4))
        self.text_box = ctk.CTkTextbox(form, height=150, fg_color=CARD_BG, border_width=1, border_color=BORDER, text_color=TEXT_PRIMARY)
        self.text_box.pack(fill="x")
        self.source_entry = self._entry(form, "Article or event URL (added automatically when sent)")
        self.image_entry = self._entry(form, "Public image URL (optional)")
        image_meta = ctk.CTkFrame(form, fg_color="transparent")
        image_meta.pack(fill="x")
        self.caption_entry = self._entry(image_meta, "Image caption", side=True)
        self.credit_entry = self._entry(image_meta, "Required image credit", side=True)
        self.rights_var = ctk.BooleanVar(value=False)
        self.rights_check = ctk.CTkCheckBox(form, text="IMAGE RIGHTS APPROVED FOR SOCIAL USE", variable=self.rights_var, text_color=TEXT_PRIMARY, border_color=TEXT_MUTED, fg_color=SUCCESS)
        self.rights_check.pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(form, text="Networks", text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", pady=(12, 4))
        networks = ctk.CTkFrame(form, fg_color="transparent")
        networks.pack(fill="x")
        for label, value in NETWORKS:
            variable = ctk.BooleanVar(value=False)
            self.network_vars[value] = variable
            ctk.CTkCheckBox(networks, text=label, variable=variable, text_color=TEXT_PRIMARY, border_color=TEXT_MUTED, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER).pack(side="left", padx=(0, 15))
        schedule = ctk.CTkFrame(form, fg_color="transparent")
        schedule.pack(fill="x", pady=(14, 0))
        self.date_entry = self._entry(schedule, "Metricool draft date/time (YYYY-MM-DD HH:MM)", side=True)
        self.timezone_entry = self._entry(schedule, "Timezone", side=True)
        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(4, 4))
        ctk.CTkButton(actions, text="SAVE LOCAL DRAFT", width=155, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self._save).pack(side="left", padx=(0, 8))
        self.send_button = ctk.CTkButton(actions, text="SEND TO METRICOOL AS DRAFT", width=230, fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER, command=self._send)
        self.send_button.pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="DELETE LOCAL DRAFT", width=160, fg_color="#475569", command=self._delete).pack(side="left")
        self.editor_status = ctk.CTkLabel(right, text="Create a local draft or import NewsDesk content.", text_color=TEXT_MUTED, anchor="w")
        self.editor_status.pack(fill="x", padx=20, pady=(0, 10))
        self._new()

    def _entry(self, parent, label, *, side=False):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(side="left" if side else "top", fill="x", expand=True, padx=(0, 8) if side else 0, pady=(8, 0))
        ctk.CTkLabel(box, text=label, text_color=TEXT_SECONDARY, anchor="w").pack(fill="x")
        entry = ctk.CTkEntry(box, fg_color=CARD_BG, border_color=BORDER, text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED)
        entry.pack(fill="x", pady=(3, 0))
        return entry

    def _show_connection_state(self):
        settings = self.settings_store.load()
        if settings["token"] and settings["user_id"] and settings["blog_id"]:
            name = settings["brand_name"] or settings["blog_id"]
            self.connection_label.configure(text=f"Metricool configured for {name}. Social profiles still need to be connected in Metricool.", text_color=SUCCESS)
        else:
            self.connection_label.configure(text="Metricool not configured yet — local Social Desk drafts are available now.", text_color=TEXT_MUTED)

    def _refresh_list(self):
        for child in self.list_frame.winfo_children(): child.destroy()
        query = self.draft_search_var.get().strip().casefold()
        selected_source = self.draft_filter_var.get().strip().upper()
        source_labels = {
            "content": "LOCAL DEMOCRACY", "events": "EVENTS",
            "planning": "PLANNING", "police": "POLICE", "fire": "FIRE",
            "sport": "SPORT", "council": "COUNCIL", "blank": "BLANK",
        }
        drafts = []
        for draft in self.drafts:
            source = source_labels.get(draft.source_kind.casefold(), "BLANK")
            if selected_source != "ALL" and source != selected_source:
                continue
            if query and query not in f"{draft.title} {draft.text} {source}".casefold():
                continue
            drafts.append((draft, source))
        for draft, source in sorted(
            drafts,
            key=lambda row: (row[0].updated_at, row[0].title.casefold()),
            reverse=True,
        ):
            label = (draft.title or draft.text or "Untitled draft").replace("\n", " ")[:48]
            try:
                updated = datetime.fromisoformat(draft.updated_at).strftime("%d/%m/%Y %H:%M")
            except (TypeError, ValueError):
                updated = "Date unavailable"
            ctk.CTkButton(
                self.list_frame,
                text=f"{label}\n{source.title()}  •  {updated}",
                anchor="w",
                height=60,
                font=("Arial", 14),
                fg_color="#334155",
                hover_color="#475569",
                command=lambda item=draft: self._load(item),
            ).pack(fill="x", pady=(0, 6))

    def _new(self):
        settings = self.settings_store.load()
        when = datetime.now() + timedelta(minutes=20)
        self.current = SocialDraft(publication_datetime=when.strftime("%Y-%m-%dT%H:%M:%S"), timezone=settings["timezone"], status="Blank social draft", source_kind="blank")
        self._populate()

    def _load(self, draft):
        self.current = draft
        self._populate()

    def _populate(self):
        draft = self.current or SocialDraft()
        draft.text = clean_social_text(draft.text, source_url=draft.source_url)
        if "ldrs.org.uk/assets/images/placeholder.png" in str(draft.image_url or "").casefold():
            draft.image_url = ""; draft.image_caption = ""; draft.image_credit = ""; draft.image_rights_status = "no image"
        for entry, value in ((self.title_entry, draft.title), (self.source_entry, draft.source_url), (self.image_entry, draft.image_url), (self.caption_entry, draft.image_caption), (self.credit_entry, draft.image_credit), (self.date_entry, draft.publication_datetime.replace("T", " ")[:16]), (self.timezone_entry, draft.timezone)):
            entry.delete(0, "end"); entry.insert(0, value)
        self.text_box.delete("1.0", "end"); self.text_box.insert("1.0", draft.text)
        self.text_box.yview_moveto(0)
        for value, variable in self.network_vars.items(): variable.set(value in draft.providers)
        self.rights_var.set(draft.image_rights_status == "approved")
        self.editor_status.configure(text=f"Status: {draft.status}")

    def _capture(self):
        draft = self.current or SocialDraft()
        draft.title = self.title_entry.get().strip()
        draft.text = self.text_box.get("1.0", "end").strip()
        draft.source_url = self.source_entry.get().strip()
        draft.image_url = self.image_entry.get().strip()
        draft.image_caption = self.caption_entry.get().strip()
        draft.image_credit = self.credit_entry.get().strip()
        draft.image_rights_status = "no image" if not draft.image_url else ("approved" if self.rights_var.get() else "not reviewed")
        draft.providers = [value for value, variable in self.network_vars.items() if variable.get()]
        raw = self.date_entry.get().strip().replace(" ", "T")
        draft.publication_datetime = raw + (":00" if len(raw) == 16 else "")
        draft.timezone = self.timezone_entry.get().strip() or "Europe/London"
        draft.updated_at = datetime.now().astimezone().isoformat()
        self.current = draft
        return draft

    def _save(self):
        draft = self._capture()
        if not draft.title and not draft.text:
            messagebox.showwarning("Social Desk", "Add a working title or post text first.", parent=self); return False
        if not any(item.draft_id == draft.draft_id for item in self.drafts): self.drafts.append(draft)
        self.store.save(self.drafts); self._refresh_list(); self.editor_status.configure(text="Local draft saved.", text_color=SUCCESS)
        return True

    def _delete(self):
        if not self.current or not any(item.draft_id == self.current.draft_id for item in self.drafts): return
        if not messagebox.askyesno("Social Desk", "Delete this local draft?", parent=self): return
        self.drafts = [item for item in self.drafts if item.draft_id != self.current.draft_id]
        self.store.save(self.drafts); self._refresh_list(); self._new()

    def _send(self):
        if not self._save(): return
        draft = self.current
        if not draft.text or not draft.providers:
            messagebox.showwarning("Social Desk", "Post text and at least one network are required.", parent=self); return
        if "instagram" in draft.providers and not draft.image_url:
            messagebox.showwarning("Social Desk", "Instagram requires an image.", parent=self); return
        if draft.image_url and not draft.image_credit:
            messagebox.showwarning("Social Desk", "Add the required image credit before sending this image.", parent=self); return
        if draft.image_url and draft.image_rights_status != "approved":
            messagebox.showwarning("Social Desk", "Confirm that the image is approved for social use before sending.", parent=self); return
        outgoing = compose_metricool_text(draft.text, source_url=draft.source_url, image_caption=draft.image_caption, image_credit=draft.image_credit)
        if "twitter" in draft.providers and len(outgoing) > 280:
            messagebox.showwarning("Social Desk", f"The X version is {len(outgoing)} characters. Reduce it to 280 or fewer.", parent=self); return
        try:
            if datetime.fromisoformat(draft.publication_datetime) <= datetime.now(): raise ValueError
        except ValueError:
            messagebox.showwarning("Social Desk", "Choose a valid future Metricool draft date and time.", parent=self); return
        settings = self.settings_store.load()
        if not settings["token"] or not settings["user_id"] or not settings["blog_id"]:
            messagebox.showinfo("Metricool not ready", "The post is safely saved locally. Connect a Metricool brand and social profiles, then complete Metricool Settings.", parent=self); return
        self.send_button.configure(state="disabled", text="SENDING DRAFT...")
        def worker():
            try:
                social_text = compose_metricool_text(
                    draft.text,
                    source_url=draft.source_url,
                    image_caption=draft.image_caption,
                    image_credit=draft.image_credit,
                )
                result = MetricoolClient(token=settings["token"], user_id=settings["user_id"], blog_id=settings["blog_id"]).create_draft(text=social_text, providers=draft.providers, publication_datetime=draft.publication_datetime, timezone=draft.timezone, image_url=draft.image_url)
                self.after(0, lambda: self._sent(result))
            except Exception as exc:
                self.after(0, lambda: self._send_failed(str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _sent(self, result):
        self.current.status = "Sent to Metricool as draft"
        if isinstance(result, dict): self.current.metricool_id = str(result.get("id") or result.get("postId") or "")
        self.store.save(self.drafts); self._refresh_list(); self.send_button.configure(state="normal", text="SEND TO METRICOOL AS DRAFT")
        self.editor_status.configure(text="Draft delivered to Metricool. Review and schedule it there.", text_color=SUCCESS)

    def _send_failed(self, detail):
        self.send_button.configure(state="normal", text="SEND TO METRICOOL AS DRAFT")
        messagebox.showerror("Metricool", detail, parent=self)

    def _settings(self):
        settings = self.settings_store.load()
        dialog = ctk.CTkToplevel(self); dialog.title("Metricool Settings"); dialog.geometry("680x570"); dialog.configure(fg_color=APP_BG); dialog.transient(self)
        panel = ctk.CTkFrame(dialog, fg_color=HEADER_BG); panel.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(panel, text="METRICOOL SETTINGS", font=("Arial", 22, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(18, 5))
        ctk.CTkLabel(panel, text="Connect social profiles in Metricool first. The token is encrypted for this Windows user and is never stored in Git.", wraplength=610, justify="left", text_color=TEXT_SECONDARY).pack(anchor="w", padx=20, pady=(0, 12))
        entries = {}
        for key, label, masked in (("token", "REST API access token", True), ("user_id", "Metricool user ID", False), ("blog_id", "Brand / blog ID", False), ("brand_name", "Brand name", False), ("timezone", "Timezone", False)):
            ctk.CTkLabel(panel, text=label, text_color=TEXT_SECONDARY).pack(anchor="w", padx=20)
            entry = ctk.CTkEntry(panel, show="*" if masked else "", fg_color=CARD_BG, border_color=BORDER, text_color=TEXT_PRIMARY); entry.pack(fill="x", padx=20, pady=(2, 9)); entry.insert(0, settings[key]); entries[key] = entry
        actions = ctk.CTkFrame(panel, fg_color="transparent"); actions.pack(fill="x", padx=20, pady=8)
        def save():
            try:
                self.settings_store.save({key: entry.get() for key, entry in entries.items()})
            except Exception as exc:
                messagebox.showerror("Metricool Settings", str(exc), parent=dialog); return
            self._show_connection_state(); dialog.destroy()
        ctk.CTkButton(actions, text="SAVE SETTINGS", command=save).pack(side="left")
        ctk.CTkButton(actions, text="CANCEL", fg_color="#475569", command=dialog.destroy).pack(side="right")
        dialog.after_idle(lambda: present_window_foreground(dialog, temporary_topmost=True))


def open_social_desk(master):
    return SocialDesk(master)
