"""Social Desk: safe local staging with optional Metricool draft delivery."""

from __future__ import annotations

from datetime import datetime, timedelta
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from newsdesk.social.metricool import MetricoolClient, MetricoolError, MetricoolImageError
from newsdesk.social.store import SocialDraft, SocialDraftStore, SocialSettingsStore
from newsdesk.social.text import clean_social_text, compose_metricool_text, repair_ldrs_draft
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
IMAGE_LIBRARY = Path(r"C:\Users\Windows\Desktop\Devour News Lincs Images")


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
        image_library = ctk.CTkFrame(form, fg_color="transparent")
        image_library.pack(fill="x", pady=(7, 0))
        ctk.CTkButton(
            image_library,
            text="IMAGE LIBRARY",
            width=145,
            fg_color=ACTION_BLUE,
            hover_color=ACTION_BLUE_HOVER,
            command=self._choose_local_image,
        ).pack(side="left", padx=(0, 10))
        self.local_image_label = ctk.CTkLabel(
            image_library,
            text="No local image selected.",
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self.local_image_label.pack(side="left", fill="x", expand=True)
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
        networks = {item for item in settings.get("connected_networks", "").split(",") if item}
        if settings["token"] and settings["user_id"] and settings["blog_id"] and settings.get("verified_at"):
            name = settings["brand_name"] or settings["blog_id"]
            facebook = "Facebook verified" if "facebook" in networks else "Facebook not connected"
            self.connection_label.configure(text=f"Metricool API verified for {name} — {facebook}.", text_color=SUCCESS if "facebook" in networks else TEXT_MUTED)
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
        if draft.source_kind == "content":
            repair_ldrs_draft(draft)
            self.store.save(self.drafts)
        self._populate()

    def _populate(self):
        draft = self.current or SocialDraft()
        # The original article URL lives in its dedicated field and is added
        # automatically at send time. Other useful URLs remain in the copy.
        excluded_url = draft.internal_source_url or draft.source_url
        draft.text = clean_social_text(draft.text, source_url=excluded_url)
        if "ldrs.org.uk/assets/images/placeholder.png" in str(draft.image_url or "").casefold():
            draft.image_url = ""; draft.image_caption = ""; draft.image_credit = ""; draft.image_rights_status = "no image"
        for entry, value in ((self.title_entry, draft.title), (self.source_entry, draft.source_url), (self.image_entry, draft.image_url), (self.caption_entry, draft.image_caption), (self.credit_entry, draft.image_credit), (self.date_entry, draft.publication_datetime.replace("T", " ")[:16]), (self.timezone_entry, draft.timezone)):
            entry.delete(0, "end"); entry.insert(0, value)
        self.text_box.delete("1.0", "end"); self.text_box.insert("1.0", draft.text)
        self.text_box.yview_moveto(0)
        for value, variable in self.network_vars.items(): variable.set(value in draft.providers)
        self.rights_var.set(draft.image_rights_status == "approved")
        local_name = Path(draft.local_image_path).name if draft.local_image_path else ""
        self.local_image_label.configure(
            text=f"Local image: {local_name}" if local_name else "No local image selected.",
            text_color=TEXT_PRIMARY if local_name else TEXT_MUTED,
        )
        self.editor_status.configure(text=f"Status: {draft.status}")

    def _choose_local_image(self):
        IMAGE_LIBRARY.mkdir(parents=True, exist_ok=True)
        selected = filedialog.askopenfilename(
            parent=self,
            title="Choose an image for this social draft",
            initialdir=str(IMAGE_LIBRARY),
            filetypes=(("Supported images", "*.jpg *.jpeg *.png"), ("JPEG images", "*.jpg *.jpeg"), ("PNG images", "*.png")),
        )
        if not selected:
            return
        draft = self.current or SocialDraft()
        draft.local_image_path = selected
        draft.image_url = ""
        self.current = draft
        self.image_entry.delete(0, "end")
        self.local_image_label.configure(text=f"Local image: {Path(selected).name}", text_color=TEXT_PRIMARY)
        self.editor_status.configure(text="Local image selected. Confirm its credit and social-use rights before sending.", text_color=TEXT_MUTED)

    def _capture(self):
        draft = self.current or SocialDraft()
        draft.title = self.title_entry.get().strip()
        draft.text = self.text_box.get("1.0", "end").strip()
        draft.source_url = self.source_entry.get().strip()
        draft.image_url = self.image_entry.get().strip()
        if draft.image_url:
            draft.local_image_path = ""
        draft.image_caption = self.caption_entry.get().strip()
        draft.image_credit = self.credit_entry.get().strip()
        has_image = bool(draft.image_url or draft.local_image_path)
        draft.image_rights_status = "no image" if not has_image else ("approved" if self.rights_var.get() else "not reviewed")
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
        if "instagram" in draft.providers and not (draft.image_url or draft.local_image_path):
            messagebox.showwarning("Social Desk", "Instagram requires an image.", parent=self); return
        has_image = bool(draft.image_url or draft.local_image_path)
        if has_image and not draft.image_credit:
            messagebox.showwarning("Social Desk", "Add the required image credit before sending this image.", parent=self); return
        if has_image and draft.image_rights_status != "approved":
            messagebox.showwarning("Social Desk", "Confirm that the image is approved for social use before sending.", parent=self); return
        outgoing_url = draft.source_url if draft.include_source_url else ""
        outgoing = compose_metricool_text(draft.text, source_url=outgoing_url, image_caption=draft.image_caption, image_credit=draft.image_credit)
        if "twitter" in draft.providers and len(outgoing) > 280:
            messagebox.showwarning("Social Desk", f"The X version is {len(outgoing)} characters. Reduce it to 280 or fewer.", parent=self); return
        try:
            if datetime.fromisoformat(draft.publication_datetime) <= datetime.now(): raise ValueError
        except ValueError:
            messagebox.showwarning("Social Desk", "Choose a valid future Metricool draft date and time.", parent=self); return
        settings = self.settings_store.load()
        if not settings["token"] or not settings["user_id"] or not settings["blog_id"]:
            messagebox.showinfo("Metricool not ready", "The post is safely saved locally. Connect a Metricool brand and social profiles, then complete Metricool Settings.", parent=self); return
        connected = {item for item in settings.get("connected_networks", "").split(",") if item}
        unavailable = sorted(set(draft.providers) - connected)
        if unavailable:
            messagebox.showwarning("Metricool profiles", f"These networks are not connected to the verified Metricool brand: {', '.join(unavailable)}.", parent=self); return
        self.send_button.configure(state="disabled", text="SENDING DRAFT...")
        def worker():
            try:
                social_text = compose_metricool_text(
                    draft.text,
                    source_url=draft.source_url if draft.include_source_url else "",
                    image_caption=draft.image_caption,
                    image_credit=draft.image_credit,
                )
                result = MetricoolClient(token=settings["token"], user_id=settings["user_id"], blog_id=settings["blog_id"]).create_draft(text=social_text, providers=draft.providers, publication_datetime=draft.publication_datetime, timezone=draft.timezone, image_url=draft.image_url, image_path=draft.local_image_path)
                self.after(0, lambda: self._sent(result))
            except MetricoolImageError as exc:
                self.after(0, lambda detail=str(exc): self._image_send_failed(detail))
            except Exception as exc:
                self.after(0, lambda detail=str(exc): self._send_failed(detail))
        threading.Thread(target=worker, daemon=True).start()

    def _sent(self, result):
        self.current.status = "Sent to Metricool as draft"
        self.current.metricool_id = MetricoolClient.draft_id(result)
        self.store.save(self.drafts); self._refresh_list(); self.send_button.configure(state="normal", text="SEND TO METRICOOL AS DRAFT")
        reference = f" ID {self.current.metricool_id}." if self.current.metricool_id else "."
        self.editor_status.configure(text=f"Draft delivered to Metricool{reference} Review it there.", text_color=SUCCESS)

    def _send_failed(self, detail):
        self.send_button.configure(state="normal", text="SEND TO METRICOOL AS DRAFT")
        messagebox.showerror("Metricool", detail, parent=self)

    def _image_send_failed(self, detail):
        self.send_button.configure(state="normal", text="SEND TO METRICOOL AS DRAFT")
        message = "Draft not sent — image could not be imported."
        self.editor_status.configure(text=message, text_color=BRAND_RED)
        messagebox.showerror("Metricool image", f"{message}\n\n{detail}\n\nThe local draft has been retained. Choose another image or remove it before trying again.", parent=self)

    def _settings(self):
        settings = self.settings_store.load()
        dialog = ctk.CTkToplevel(self); dialog.title("Metricool Settings"); dialog.geometry("720x700"); dialog.configure(fg_color=APP_BG); dialog.transient(self)
        panel = ctk.CTkFrame(dialog, fg_color=HEADER_BG); panel.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(panel, text="METRICOOL SETTINGS", font=("Arial", 22, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(18, 5))
        ctk.CTkLabel(panel, text="Enter the REST API token and user ID, then test the connection. NewsDesk retrieves your actual Metricool brands and connected social profiles.", wraplength=650, justify="left", text_color=TEXT_SECONDARY).pack(anchor="w", padx=20, pady=(0, 12))
        entries = {}
        for key, label, masked in (("token", "REST API access token", True), ("user_id", "Metricool user ID", False), ("timezone", "Timezone", False)):
            ctk.CTkLabel(panel, text=label, text_color=TEXT_SECONDARY).pack(anchor="w", padx=20)
            entry = ctk.CTkEntry(panel, show="*" if masked else "", fg_color=CARD_BG, border_color=BORDER, text_color=TEXT_PRIMARY)
            entry.pack(fill="x", padx=20, pady=(2, 9)); entry.insert(0, settings[key]); entries[key] = entry
        ctk.CTkLabel(panel, text="Verified Metricool brand", text_color=TEXT_SECONDARY).pack(anchor="w", padx=20)
        initial = settings["brand_name"] or "Test connection first"
        brand_var = ctk.StringVar(value=initial)
        brand_menu = ctk.CTkOptionMenu(panel, values=[initial], variable=brand_var, state="disabled")
        brand_menu.pack(fill="x", padx=20, pady=(2, 9))
        status = ctk.CTkLabel(panel, text="Connection not tested in this window.", wraplength=650, justify="left", anchor="w", text_color=TEXT_MUTED)
        status.pack(fill="x", padx=20, pady=(5, 10))
        verified = {}
        actions = ctk.CTkFrame(panel, fg_color="transparent"); actions.pack(fill="x", padx=20, pady=8)
        test_button = ctk.CTkButton(actions, text="TEST CONNECTION"); test_button.pack(side="left", padx=(0, 8))
        facebook_button = ctk.CTkButton(actions, text="SEND FACEBOOK TEST DRAFT", fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER, state="disabled")
        facebook_button.pack(side="left")

        def chosen(): return verified.get(brand_var.get())
        def show_brand(_value=None):
            brand = chosen(); facebook = (brand or {}).get("networks", {}).get("facebook")
            facebook_button.configure(state="normal" if facebook else "disabled")
            status.configure(text=f"Facebook connected as {facebook}." if facebook else "Selected brand has no Facebook connection.", text_color=SUCCESS if facebook else TEXT_MUTED)
        brand_menu.configure(command=show_brand)

        def connection_done(brands):
            test_button.configure(state="normal", text="TEST CONNECTION"); verified.clear()
            for brand in brands: verified[f"{brand['name']} (ID {brand['id']})"] = brand
            choices = list(verified); brand_menu.configure(values=choices, state="normal")
            selected = next((label for label, brand in verified.items() if brand["id"] == settings["blog_id"]), choices[0])
            brand_var.set(selected); show_brand()
        def connection_failed(detail):
            test_button.configure(state="normal", text="TEST CONNECTION"); status.configure(text=detail, text_color=BRAND_RED)
        def test_connection():
            token = entries["token"].get().strip(); user_id = entries["user_id"].get().strip()
            if not token or not user_id:
                messagebox.showwarning("Metricool Settings", "Enter the REST API token and Metricool user ID.", parent=dialog); return
            test_button.configure(state="disabled", text="TESTING...")
            def worker():
                try:
                    brands = MetricoolClient(token=token, user_id=user_id).connection_details()
                    dialog.after(0, lambda value=brands: connection_done(value))
                except Exception as exc:
                    detail = str(exc); dialog.after(0, lambda value=detail: connection_failed(value))
            threading.Thread(target=worker, daemon=True).start()
        test_button.configure(command=test_connection)

        def test_facebook():
            brand = chosen(); facebook = (brand or {}).get("networks", {}).get("facebook")
            if not facebook or not messagebox.askyesno("Metricool test draft", f"Create one unpublished Facebook test draft for {facebook}?", parent=dialog): return
            facebook_button.configure(state="disabled", text="SENDING TEST...")
            def worker():
                try:
                    when = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
                    result = MetricoolClient(token=entries["token"].get(), user_id=brand["user_id"], blog_id=brand["id"]).create_draft(text="NewsDesk Pro Metricool connection test — unpublished draft.", providers=["facebook"], publication_datetime=when, timezone=entries["timezone"].get().strip() or brand["timezone"])
                    reference = MetricoolClient.draft_id(result) or "returned without an ID"
                    dialog.after(0, lambda value=reference: test_done(value))
                except Exception as exc:
                    detail = str(exc); dialog.after(0, lambda value=detail: test_failed(value))
            threading.Thread(target=worker, daemon=True).start()
        def test_done(reference):
            facebook_button.configure(state="normal", text="SEND FACEBOOK TEST DRAFT"); status.configure(text=f"Facebook test draft created successfully. Metricool reference: {reference}.", text_color=SUCCESS)
        def test_failed(detail):
            facebook_button.configure(state="normal", text="SEND FACEBOOK TEST DRAFT"); messagebox.showerror("Metricool test draft", detail, parent=dialog)
        facebook_button.configure(command=test_facebook)

        save_row = ctk.CTkFrame(panel, fg_color="transparent"); save_row.pack(fill="x", padx=20, pady=(12, 8))
        def save():
            brand = chosen()
            if not brand:
                messagebox.showwarning("Metricool Settings", "Test the connection and select a verified brand before saving.", parent=dialog); return
            try:
                self.settings_store.save({"token": entries["token"].get(), "user_id": brand["user_id"], "blog_id": brand["id"], "brand_name": brand["name"], "timezone": entries["timezone"].get() or brand["timezone"], "verified_at": datetime.now().astimezone().isoformat(), "connected_networks": ",".join(sorted(brand["networks"]))})
            except Exception as exc:
                messagebox.showerror("Metricool Settings", str(exc), parent=dialog); return
            self._show_connection_state(); dialog.destroy()
        ctk.CTkButton(save_row, text="SAVE VERIFIED SETTINGS", command=save).pack(side="left")
        ctk.CTkButton(save_row, text="CANCEL", fg_color="#475569", command=dialog.destroy).pack(side="right")
        dialog.after_idle(lambda: present_window_foreground(dialog, temporary_topmost=True))

def open_social_desk(master):
    return SocialDesk(master)
