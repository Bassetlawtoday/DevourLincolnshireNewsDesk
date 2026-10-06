from __future__ import annotations

from datetime import date

from .config import JobsPublication, load_publications
from .models import Vacancy, VacancyStatus, utc_now
from .rendering import facebook_post
from .repository import JobsRepository
from .validation import ValidationIssue, VacancyValidator


class JobsService:
    EDITABLE_FIELDS = {
        "job_title", "area", "location_detail", "salary_text", "hours_text",
        "contract_type", "workplace_type", "positions", "description",
        "requirements", "benefits", "application_url", "application_email",
        "closing_date", "employer_name", "employer_legal_name",
        "employer_website", "company_number",
    }
    def __init__(self, *, repository: JobsRepository | None = None, publications=None):
        self.repository = repository or JobsRepository()
        self.publications: dict[str, JobsPublication] = publications or load_publications()
        self.validator = VacancyValidator()

    def submit(self, vacancy: Vacancy) -> tuple[Vacancy, list[ValidationIssue]]:
        publication = self.publications[vacancy.publication_key]
        issues = self.validator.validate(vacancy, publication)
        if any(issue.blocking for issue in issues):
            return vacancy, issues
        vacancy.status = VacancyStatus.SUBMITTED.value
        self.repository.save(vacancy, action="submitted", actor=vacancy.submitter_email)
        return vacancy, issues

    def approve(self, vacancy_id: str, *, editor: str) -> Vacancy:
        vacancy = self._required(vacancy_id)
        issues = self.validator.validate(vacancy, self.publications[vacancy.publication_key])
        if issues:
            raise ValueError("Vacancy still has validation or editorial-review issues.")
        vacancy.status = VacancyStatus.APPROVED.value
        vacancy.approved_at = utc_now()
        vacancy.approved_by = editor.strip()
        self.repository.save(vacancy, action="approved", actor=editor)
        return vacancy

    def reject(self, vacancy_id: str, *, editor: str, reason: str) -> Vacancy:
        if not reason.strip():
            raise ValueError("A rejection reason is required.")
        vacancy = self._required(vacancy_id)
        vacancy.status = VacancyStatus.REJECTED.value
        vacancy.editorial_note = reason.strip()
        self.repository.save(vacancy, action="rejected", actor=editor, detail=reason.strip())
        return vacancy

    def request_changes(self, vacancy_id: str, *, editor: str, reason: str) -> Vacancy:
        if not reason.strip():
            raise ValueError("Explain what the advertiser needs to change.")
        vacancy = self._required(vacancy_id)
        vacancy.status = VacancyStatus.NEEDS_CHANGES.value
        vacancy.editorial_note = reason.strip()
        self.repository.save(vacancy, action="changes_requested", actor=editor, detail=reason.strip())
        return vacancy

    def update(self, vacancy_id: str, *, editor: str, changes: dict) -> tuple[Vacancy, list[ValidationIssue]]:
        vacancy = self._required(vacancy_id)
        for field, value in changes.items():
            if field in self.EDITABLE_FIELDS:
                setattr(vacancy, field, int(value) if field == "positions" else str(value).strip())
        vacancy.status = VacancyStatus.SUBMITTED.value
        issues = self.validator.validate(vacancy, self.publications[vacancy.publication_key])
        self.repository.save(vacancy, action="edited", actor=editor, detail="Editorial vacancy fields updated")
        return vacancy, issues

    def metricool_copy(self, vacancy_id: str) -> str:
        vacancy = self._required(vacancy_id)
        if vacancy.status not in {VacancyStatus.APPROVED.value, VacancyStatus.SENT_TO_METRICOOL.value}:
            raise ValueError("Only an approved vacancy can be prepared for Metricool.")
        return facebook_post(vacancy, self.publications[vacancy.publication_key])

    def mark_metricool(self, vacancy_id: str, *, metricool_id: str, editor: str) -> Vacancy:
        vacancy = self._required(vacancy_id)
        if vacancy.status != VacancyStatus.APPROVED.value:
            raise ValueError("Only an approved vacancy can be sent to Metricool.")
        vacancy.metricool_id = metricool_id.strip()
        vacancy.status = VacancyStatus.SENT_TO_METRICOOL.value
        self.repository.save(vacancy, action="sent_to_metricool", actor=editor, detail=vacancy.metricool_id)
        return vacancy

    def apply_destination(self, token: str) -> str:
        vacancy = self.repository.by_apply_token(token)
        if vacancy is None:
            raise LookupError("Vacancy was not found.")
        if vacancy.status not in {VacancyStatus.APPROVED.value, VacancyStatus.SENT_TO_METRICOOL.value}:
            raise LookupError("Vacancy is not currently open.")
        if vacancy.closing_date and vacancy.closing_date < date.today().isoformat():
            raise LookupError("Vacancy has closed.")
        self.repository.record_apply_click(vacancy.vacancy_id)
        if vacancy.application_url.strip():
            return vacancy.application_url.strip()
        return f"mailto:{vacancy.application_email.strip()}?subject=Application%20for%20{vacancy.job_title.replace(' ', '%20')}"

    def _required(self, vacancy_id: str) -> Vacancy:
        vacancy = self.repository.get(vacancy_id)
        if vacancy is None:
            raise LookupError("Vacancy was not found.")
        return vacancy
