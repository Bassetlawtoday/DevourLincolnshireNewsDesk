from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import threading
from tkinter import messagebox

import customtkinter as ctk

from newsdesk.jobs.config import load_publications
from newsdesk.jobs.client import JobsApiClient
from newsdesk.jobs.models import VacancyStatus
from newsdesk.jobs.rendering import facebook_post
from newsdesk.jobs.repository import JobsRepository
from newsdesk.jobs.service import JobsService
from newsdesk.jobs.settings import JobsSettingsStore
from newsdesk.jobs.weekly import weekly_vacancy_list
from newsdesk.social.metricool import MetricoolClient
from newsdesk.social.store import SocialSettingsStore
from newsdesk.theme import APP_BG, HEADER_BG, CARD_BG, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, ACTION_BLUE, ACTION_BLUE_HOVER, BRAND_RED, BRAND_RED_HOVER, SUCCESS


class JobsDesk(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.transient(master)
        self.title("Jobs Desk — NewsDesk Pro")
        self.geometry("1500x900")
        self.configure(fg_color=APP_BG)
        self.publications = load_publications()
        self.settings_store = JobsSettingsStore()
        self.settings = self.settings_store.load()
        self.publication_key = self.settings["publication_key"]
        self.repository = JobsRepository()
        self.service = JobsService(repository=self.repository, publications=self.publications)
        self.api = JobsApiClient(self.settings["api_url"], self.settings["api_token"]) if self.settings["api_url"] and self.settings["api_token"] else None
        self.vacancies = []
        self.clicks = {}
        self.current = None
        self._build()
        self.refresh()
        self.after(75, self._bring_to_front)

    def _bring_to_front(self):
        try:
            self.deiconify()
            self.state("zoomed")
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _build(self):
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0, height=110)
        header.pack(fill="x"); header.pack_propagate(False)
        ctk.CTkLabel(header, text="JOBS DESK", font=("Arial", 30, "bold"), text_color=TEXT_PRIMARY).pack(side="left", padx=30)
        ctk.CTkLabel(header, text="Employer adverts • editorial approval • Metricool drafts", text_color=TEXT_SECONDARY).pack(side="left")
        ctk.CTkButton(header, text="CLOSE", width=100, fg_color="#475569", command=self.destroy).pack(side="right", padx=24)
        ctk.CTkButton(header, text="SETTINGS", width=105, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.open_settings).pack(side="right", padx=8)
        ctk.CTkButton(header, text="REFRESH", width=110, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.refresh).pack(side="right", padx=8)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=18)
        left = ctk.CTkFrame(body, width=430, fg_color=HEADER_BG, border_width=1, border_color=BORDER)
        left.pack(side="left", fill="y", padx=(0, 14)); left.pack_propagate(False)
        filters = ctk.CTkFrame(left, fg_color="transparent"); filters.pack(fill="x", padx=14, pady=14)
        self.status = ctk.CTkOptionMenu(filters, values=["All", "Submitted", "Needs changes", "Approved", "Sent to Metricool", "Rejected", "Expired"], command=lambda _v: self._render_list(), fg_color=ACTION_BLUE, button_color=ACTION_BLUE)
        self.status.pack(side="left", fill="x", expand=True)
        self.count = ctk.CTkLabel(filters, text="0", text_color=TEXT_SECONDARY); self.count.pack(side="right", padx=(12,0))
        self.list_frame = ctk.CTkScrollableFrame(left, fg_color=CARD_BG)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=(0,12))

        right = ctk.CTkFrame(body, fg_color=HEADER_BG, border_width=1, border_color=BORDER)
        right.pack(side="left", fill="both", expand=True)
        actions = ctk.CTkFrame(right, fg_color="transparent"); actions.pack(fill="x", padx=18, pady=14)
        primary = ctk.CTkFrame(actions, fg_color="transparent"); primary.pack(fill="x")
        secondary = ctk.CTkFrame(actions, fg_color="transparent"); secondary.pack(fill="x", pady=(8,0))
        self.approve_button = ctk.CTkButton(primary, text="APPROVE", fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.approve)
        self.approve_button.pack(side="left", padx=(0,8))
        ctk.CTkButton(primary, text="EDIT VACANCY", fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.edit_vacancy).pack(side="left", padx=(0,8))
        ctk.CTkButton(primary, text="REQUEST CHANGES", fg_color="#475569", command=self.request_changes).pack(side="left", padx=(0,8))
        ctk.CTkButton(primary, text="REJECT", fg_color="#475569", command=self.reject).pack(side="left")
        self.metricool_button = ctk.CTkButton(secondary, text="SEND FACEBOOK DRAFT TO METRICOOL", width=260, fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER, command=self.send_metricool)
        self.metricool_button.pack(side="left", padx=(0,8))
        ctk.CTkButton(secondary, text="COPY WEEKLY LIST", fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=self.copy_weekly).pack(side="left")
        self.detail = ctk.CTkTextbox(right, fg_color=CARD_BG, border_width=1, border_color=BORDER, text_color=TEXT_PRIMARY, font=("Arial", 15), wrap="word")
        self.detail.pack(fill="both", expand=True, padx=18, pady=(0,12))
        self.message = ctk.CTkLabel(right, text="Select a vacancy to review.", text_color=TEXT_MUTED, anchor="w")
        self.message.pack(fill="x", padx=18, pady=(0,14))

    def refresh(self):
        statuses = tuple(status.value for status in VacancyStatus)
        try:
            if self.api:
                self.vacancies, self.clicks = self.api.vacancies(self.publication_key, statuses)
            else:
                self.vacancies = self.repository.list(self.publication_key, statuses=statuses)
                self.clicks = self.repository.click_totals(self.publication_key)
        except Exception as exc:
            self.message.configure(text=f"Could not load the hosted Jobs Desk: {exc}", text_color=BRAND_RED)
            return
        self._render_list()

    def _render_list(self):
        for child in self.list_frame.winfo_children(): child.destroy()
        selected = self.status.get().casefold().replace(" ", "_")
        rows = self.vacancies if selected == "all" else [v for v in self.vacancies if v.status == selected]
        self.count.configure(text=f"{len(rows)} adverts")
        for vacancy in rows:
            clicks = int(self.clicks.get(vacancy.vacancy_id, 0))
            ctk.CTkButton(self.list_frame, text=f"{vacancy.job_title}\n📍 {vacancy.area} • {vacancy.employer_name}\n{vacancy.status.replace('_',' ').title()} • {clicks} apply clicks", anchor="w", height=78, fg_color="#334155", hover_color="#475569", command=lambda item=vacancy: self.select(item)).pack(fill="x", pady=(0,7))

    def select(self, vacancy):
        self.current = vacancy
        publication = self.publications[vacancy.publication_key]
        issues = self.service.validator.validate(vacancy, publication)
        review = "\n".join(f"• {i.message}" for i in issues) or "No validation issues."
        manual = "• Confirm that the selected area and detailed location agree.\n• Verify the employer and application destination independently.\n• Check that pay, hours and closing date match the employer's evidence."
        copy = facebook_post(vacancy, publication) if vacancy.status in {VacancyStatus.APPROVED.value, VacancyStatus.SENT_TO_METRICOOL.value} else "The final Facebook copy is generated after approval."
        content = f"{vacancy.job_title}\n\nAREA\n{vacancy.area} — {vacancy.location_detail}\n\nEMPLOYER\n{vacancy.employer_name}\nWebsite: {vacancy.employer_website or 'Not supplied'}\nSubmitted by: {vacancy.submitter_name} <{vacancy.submitter_email}>\n\nVACANCY\nPay: {vacancy.salary_text}\nHours: {vacancy.hours_text}\nContract: {vacancy.contract_type} • {vacancy.workplace_type}\nClosing: {vacancy.closing_date}\nApply: {vacancy.application_url or vacancy.application_email}\n\nDESCRIPTION\n{vacancy.description}\n\nREQUIREMENTS\n{vacancy.requirements or 'Not supplied'}\n\nBENEFITS\n{vacancy.benefits or 'Not supplied'}\n\nAUTOMATIC CHECKS\n{review}\n\nMANUAL EDITORIAL CHECKS\n{manual}\n\nFACEBOOK DRAFT\n{copy}"
        self.detail.delete("1.0", "end"); self.detail.insert("1.0", content); self.detail.yview_moveto(0)
        self.message.configure(text=f"Status: {vacancy.status.replace('_',' ').title()} • {int(self.clicks.get(vacancy.vacancy_id, 0))} outbound Apply Now clicks", text_color=TEXT_SECONDARY)

    def approve(self):
        if not self.current: return
        try:
            self.current = self.api.action(self.current.vacancy_id, "approve", editor=self.settings["editor_name"]) if self.api else self.service.approve(self.current.vacancy_id, editor=self.settings["editor_name"])
        except (ValueError, LookupError) as exc:
            messagebox.showwarning("Jobs Desk", str(exc), parent=self); return
        self.refresh(); self.select(self.current)
        self.message.configure(text="Vacancy approved and ready for Metricool.", text_color=SUCCESS)

    def reject(self):
        if not self.current: return
        dialog = ctk.CTkInputDialog(text="Reason for rejection:", title="Reject vacancy")
        reason = dialog.get_input() or ""
        if not reason.strip(): return
        if self.api: self.api.action(self.current.vacancy_id, "reject", editor=self.settings["editor_name"], reason=reason)
        else: self.service.reject(self.current.vacancy_id, editor=self.settings["editor_name"], reason=reason)
        self.refresh(); self.detail.delete("1.0", "end"); self.current = None

    def request_changes(self):
        if not self.current: return
        dialog = ctk.CTkInputDialog(text="Explain clearly what the advertiser must correct:", title="Request changes")
        reason = dialog.get_input() or ""
        if not reason.strip(): return
        if self.api: self.api.action(self.current.vacancy_id, "request_changes", editor=self.settings["editor_name"], reason=reason)
        else: self.service.request_changes(self.current.vacancy_id, editor=self.settings["editor_name"], reason=reason)
        self.refresh(); self.detail.delete("1.0", "end"); self.current = None
        self.message.configure(text="Changes requested. The reason is stored in the audit record.", text_color=SUCCESS)

    def edit_vacancy(self):
        if not self.current: return
        vacancy = self.current
        dialog = ctk.CTkToplevel(self); dialog.title("Edit vacancy"); dialog.geometry("850x820"); dialog.configure(fg_color=APP_BG); dialog.transient(self); dialog.grab_set()
        panel = ctk.CTkScrollableFrame(dialog, fg_color=HEADER_BG); panel.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(panel, text="EDIT VACANCY", font=("Arial", 23, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=16, pady=(14,4))
        ctk.CTkLabel(panel, text="Edits are saved to the audit record and the vacancy returns to Submitted for checking.", text_color=TEXT_SECONDARY).pack(anchor="w", padx=16, pady=(0,14))
        specifications = (
            ("job_title", "Job title (2–14 words)", 1), ("area", "Area", 1),
            ("location_detail", "Detailed work location", 1), ("employer_name", "Employer name", 1),
            ("employer_website", "Employer website", 1), ("salary_text", "Salary or pay range", 1),
            ("hours_text", "Hours", 1), ("contract_type", "Contract type", 1),
            ("workplace_type", "Workplace type", 1), ("positions", "Number of positions", 1),
            ("closing_date", "Closing date (YYYY-MM-DD)", 1), ("application_url", "Application URL", 1),
            ("application_email", "Application email", 1), ("description", "Description (40–180 words)", 7),
            ("requirements", "Requirements (5–80 words, optional)", 5), ("benefits", "Benefits (3–60 words, optional)", 4),
        )
        controls = {}
        for field, label, lines in specifications:
            ctk.CTkLabel(panel, text=label, text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=16)
            value = str(getattr(vacancy, field) or "")
            if lines == 1:
                control = ctk.CTkEntry(panel, fg_color=CARD_BG, border_color=BORDER, text_color=TEXT_PRIMARY)
                control.insert(0, value)
            else:
                control = ctk.CTkTextbox(panel, height=lines * 28, fg_color=CARD_BG, border_width=1, border_color=BORDER, text_color=TEXT_PRIMARY, wrap="word")
                control.insert("1.0", value)
            control.pack(fill="x", padx=16, pady=(3,10)); controls[field] = control
        def save():
            changes = {}
            for field, _label, lines in specifications:
                changes[field] = controls[field].get().strip() if lines == 1 else controls[field].get("1.0", "end").strip()
            try:
                updated = self.api.action(vacancy.vacancy_id, "update", editor=self.settings["editor_name"], changes=changes) if self.api else self.service.update(vacancy.vacancy_id, editor=self.settings["editor_name"], changes=changes)[0]
            except (ValueError, LookupError, OSError) as exc:
                messagebox.showerror("Edit vacancy", str(exc), parent=dialog); return
            dialog.destroy(); self.current = updated; self.refresh(); self.select(updated)
            self.message.configure(text="Edits saved. Review the automatic and manual checks before approval.", text_color=SUCCESS)
        ctk.CTkButton(panel, text="SAVE CHANGES", height=42, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=save).pack(anchor="w", padx=16, pady=(6,18))
        dialog.after(75, lambda: (dialog.lift(), dialog.focus_force()))

    def send_metricool(self):
        if not self.current: return
        if self.current.status not in {VacancyStatus.APPROVED.value, VacancyStatus.SENT_TO_METRICOOL.value}:
            messagebox.showwarning("Jobs Desk", "Only an approved vacancy can be sent to Metricool.", parent=self); return
        text = facebook_post(self.current, self.publications[self.current.publication_key])
        settings = SocialSettingsStore(Path("data") / "jobs_metricool.json").load()
        if not all(settings.get(key) for key in ("token", "user_id", "blog_id")):
            messagebox.showwarning("Jobs Desk", "Connect the Jobs Metricool brand in Social Desk settings first.", parent=self); return
        when = (datetime.now() + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S")
        self.metricool_button.configure(state="disabled", text="SENDING DRAFT…")
        vacancy_id = self.current.vacancy_id
        def worker():
            try:
                result = MetricoolClient(token=settings["token"], user_id=settings["user_id"], blog_id=settings["blog_id"]).create_draft(text=text, providers=["facebook"], publication_datetime=when, timezone=settings.get("timezone") or "Europe/London")
                metricool_id = MetricoolClient.draft_id(result)
                self.after(0, lambda: self._sent(vacancy_id, metricool_id))
            except Exception as exc:
                self.after(0, lambda detail=str(exc): self._send_failed(detail))
        threading.Thread(target=worker, daemon=True).start()

    def _sent(self, vacancy_id, metricool_id):
        self.current = self.api.action(vacancy_id, "metricool", metricool_id=metricool_id, editor=self.settings["editor_name"]) if self.api else self.service.mark_metricool(vacancy_id, metricool_id=metricool_id, editor=self.settings["editor_name"])
        self.metricool_button.configure(state="normal", text="SEND FACEBOOK DRAFT TO METRICOOL")
        self.refresh(); self.select(self.current)
        self.message.configure(text="Facebook advert delivered to Metricool as a draft for editorial review.", text_color=SUCCESS)

    def _send_failed(self, detail):
        self.metricool_button.configure(state="normal", text="SEND FACEBOOK DRAFT TO METRICOOL")
        messagebox.showerror("Metricool", detail, parent=self)

    def copy_weekly(self):
        report = weekly_vacancy_list(self.vacancies, self.publications[self.publication_key])
        self.clipboard_clear(); self.clipboard_append(report)
        self.message.configure(text="Weekly vacancy list copied, grouped by area.", text_color=SUCCESS)

    def open_settings(self):
        dialog = ctk.CTkToplevel(self); dialog.title("Jobs Desk Settings"); dialog.geometry("760x760"); dialog.configure(fg_color=APP_BG); dialog.transient(self); dialog.grab_set()
        panel = ctk.CTkScrollableFrame(dialog, fg_color=HEADER_BG); panel.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(panel, text="JOBS DESK SETTINGS", font=("Arial", 23, "bold"), text_color=TEXT_PRIMARY).pack(anchor="w", padx=18, pady=(16,5))
        ctk.CTkLabel(panel, text="The Jobs Metricool brand is stored separately from the news brand.", text_color=TEXT_SECONDARY).pack(anchor="w", padx=18, pady=(0,16))
        current_jobs = self.settings_store.load()
        current_metricool = SocialSettingsStore(Path("data") / "jobs_metricool.json").load()
        entries = {}
        fields = (
            ("api_url", "Hosted Jobs service URL", current_jobs["api_url"], False),
            ("api_token", "Hosted Jobs editorial API token", current_jobs["api_token"], True),
            ("editor_name", "Editor name for the audit log", current_jobs["editor_name"], False),
            ("metricool_token", "Jobs Metricool API token", current_metricool["token"], True),
            ("metricool_user_id", "Jobs Metricool user ID", current_metricool["user_id"], False),
            ("metricool_blog_id", "Jobs Metricool brand/blog ID", current_metricool["blog_id"], False),
            ("timezone", "Timezone", current_metricool.get("timezone") or "Europe/London", False),
        )
        for key, label, value, secret in fields:
            ctk.CTkLabel(panel, text=label, text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=18)
            entry = ctk.CTkEntry(panel, show="*" if secret else "", fg_color=CARD_BG, border_color=BORDER, text_color=TEXT_PRIMARY)
            entry.pack(fill="x", padx=18, pady=(3,11)); entry.insert(0, value); entries[key] = entry
        def save():
            jobs_values = {"api_url": entries["api_url"].get(), "api_token": entries["api_token"].get(), "publication_key": self.publication_key, "editor_name": entries["editor_name"].get()}
            metricool_values = {"token": entries["metricool_token"].get(), "user_id": entries["metricool_user_id"].get(), "blog_id": entries["metricool_blog_id"].get(), "brand_name": "Devour Jobs", "timezone": entries["timezone"].get(), "verified_at": "", "connected_networks": "facebook"}
            try:
                self.settings_store.save(jobs_values)
                SocialSettingsStore(Path("data") / "jobs_metricool.json").save(metricool_values)
            except Exception as exc:
                messagebox.showerror("Jobs Desk Settings", str(exc), parent=dialog); return
            self.settings = self.settings_store.load()
            self.api = JobsApiClient(self.settings["api_url"], self.settings["api_token"]) if self.settings["api_url"] and self.settings["api_token"] else None
            dialog.destroy(); self.refresh()
        button_row = ctk.CTkFrame(panel, fg_color="transparent"); button_row.pack(fill="x", padx=18, pady=(8,18))
        ctk.CTkButton(button_row, text="SAVE SETTINGS", height=40, fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=save).pack(side="left", padx=(0,8))
        test_status = ctk.CTkLabel(panel, text="", text_color=TEXT_MUTED, anchor="w"); test_status.pack(fill="x", padx=18, pady=(0,18))
        def test_connection():
            url, token = entries["api_url"].get().strip(), entries["api_token"].get().strip()
            if not url or not token:
                test_status.configure(text="Enter the service URL and editorial token first.", text_color=BRAND_RED); return
            test_status.configure(text="Testing hosted Jobs service…", text_color=TEXT_MUTED)
            def worker():
                try:
                    JobsApiClient(url, token).vacancies(self.publication_key, (VacancyStatus.SUBMITTED.value,))
                    self.after(0, lambda: test_status.configure(text="Connection verified — URL and editorial token are correct.", text_color=SUCCESS))
                except Exception as exc:
                    self.after(0, lambda detail=str(exc): test_status.configure(text=f"Connection failed: {detail}", text_color=BRAND_RED))
            threading.Thread(target=worker, daemon=True).start()
        ctk.CTkButton(button_row, text="TEST HOSTED SERVICE", height=40, fg_color="#475569", command=test_connection).pack(side="left")
        dialog.after(75, lambda: (dialog.lift(), dialog.focus_force()))


def open_jobs_desk(master):
    return JobsDesk(master)
