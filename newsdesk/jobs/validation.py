from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from urllib.parse import urlsplit

from .config import JobsPublication
from .models import Vacancy


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    field: str
    message: str
    blocking: bool = True


class VacancyValidator:
    WORD_LIMITS = {
        "job_title": (2, 14, "Job title"),
        "description": (40, 180, "Vacancy description"),
        "requirements": (5, 80, "Requirements"),
        "benefits": (3, 60, "Benefits"),
    }
    CHARACTER_LIMITS = {
        "employer_name": (2, 100, "Employer name"),
        "location_detail": (2, 120, "Work location"),
        "salary_text": (2, 100, "Salary or pay range"),
        "hours_text": (1, 100, "Hours"),
    }
    CONTRACT_TYPES = {
        "Permanent", "Fixed term", "Temporary", "Apprenticeship",
        "Contract", "Casual", "Volunteer",
    }
    WORKPLACE_TYPES = {"On site", "Hybrid", "Remote"}
    SUSPICIOUS_TERMS = (
        "pay to apply", "application fee", "training fee required",
        "guaranteed earnings", "unlimited earnings", "crypto payment",
        "whatsapp only", "telegram only",
    )
    REVIEW_TERMS = (
        "young person", "young and energetic", "recent graduate only",
        "male only", "female only", "native english speaker",
        "able-bodied", "no disabilities",
    )

    def validate(
        self, vacancy: Vacancy, publication: JobsPublication, *, today: date | None = None
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        required = {
            "employer_name": "Employer name",
            "submitter_name": "Submitter name",
            "submitter_email": "Work email",
            "job_title": "Job title",
            "area": "Area",
            "location_detail": "Work location",
            "salary_text": "Salary or pay range",
            "hours_text": "Hours",
            "contract_type": "Contract type",
            "workplace_type": "Workplace type",
            "description": "Job description",
            "closing_date": "Closing date",
        }
        for field_name, label in required.items():
            if not str(getattr(vacancy, field_name, "") or "").strip():
                issues.append(ValidationIssue(field_name, f"{label} is required."))
        for field_name, (minimum, maximum, label) in self.WORD_LIMITS.items():
            value = str(getattr(vacancy, field_name, "") or "").strip()
            if not value and field_name in {"requirements", "benefits"}:
                continue
            words = self._word_count(value)
            if value and words < minimum:
                issues.append(ValidationIssue(field_name, f"{label} must contain at least {minimum} words."))
            if words > maximum:
                issues.append(ValidationIssue(field_name, f"{label} must contain no more than {maximum} words."))
        for field_name, (minimum, maximum, label) in self.CHARACTER_LIMITS.items():
            value = str(getattr(vacancy, field_name, "") or "").strip()
            if value and len(value) < minimum:
                issues.append(ValidationIssue(field_name, f"{label} is too short."))
            if len(value) > maximum:
                issues.append(ValidationIssue(field_name, f"{label} must contain no more than {maximum} characters."))
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", vacancy.submitter_email.strip()):
            issues.append(ValidationIssue("submitter_email", "Enter a valid work email address."))
        if not (vacancy.application_url.strip() or vacancy.application_email.strip()):
            issues.append(ValidationIssue("application", "Provide an application URL or application email."))
        if vacancy.application_url and not self._safe_https_url(vacancy.application_url):
            issues.append(ValidationIssue("application_url", "The application URL must be a complete HTTPS address."))
        if vacancy.employer_website and not self._safe_https_url(vacancy.employer_website):
            issues.append(ValidationIssue("employer_website", "The employer website must be a complete HTTPS address."))
        if vacancy.application_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", vacancy.application_email.strip()):
            issues.append(ValidationIssue("application_email", "Enter a valid application email address."))
        if vacancy.contract_type and vacancy.contract_type not in self.CONTRACT_TYPES:
            issues.append(ValidationIssue("contract_type", "Select a recognised contract type."))
        if vacancy.workplace_type and vacancy.workplace_type not in self.WORKPLACE_TYPES:
            issues.append(ValidationIssue("workplace_type", "Select on site, hybrid or remote."))
        if vacancy.hours_text and not re.search(
            r"\b(hour|hours|day|days|week|weeks|shift|shifts|flexible|full[ -]?time|part[ -]?time)\b",
            vacancy.hours_text,
            flags=re.IGNORECASE,
        ):
            issues.append(ValidationIssue("hours_text", "Explain the hours, for example: 37 hours per week or flexible part-time hours."))
        if vacancy.positions < 1 or vacancy.positions > 999:
            issues.append(ValidationIssue("positions", "Number of positions must be between 1 and 999."))
        try:
            closing = date.fromisoformat(vacancy.closing_date)
            if closing < (today or date.today()):
                issues.append(ValidationIssue("closing_date", "Closing date cannot be in the past."))
        except ValueError:
            if vacancy.closing_date:
                issues.append(ValidationIssue("closing_date", "Closing date must be a valid date."))
        if vacancy.area not in publication.core_areas:
            if not publication.allow_outside_area:
                issues.append(ValidationIssue("area", "This publication does not accept vacancies outside its core area."))
            elif not vacancy.outside_core_area:
                issues.append(ValidationIssue("outside_core_area", "Confirm that this vacancy is outside the publication's core area."))
        declarations = {
            "submitter_authorised": "Confirm that you are authorised to submit this vacancy.",
            "genuine_vacancy_confirmed": "Confirm that this is a genuine vacancy.",
            "equality_confirmed": "Confirm that the advertisement complies with equality law.",
            "terms_accepted": "Accept the advertising terms.",
        }
        for field_name, message in declarations.items():
            if not getattr(vacancy, field_name):
                issues.append(ValidationIssue(field_name, message))
        combined = " ".join((vacancy.job_title, vacancy.description, vacancy.requirements)).casefold()
        if self._looks_meaningless(vacancy.description):
            issues.append(ValidationIssue("description", "The vacancy description does not appear to contain meaningful prose."))
        for term in self.SUSPICIOUS_TERMS:
            if term in combined:
                issues.append(ValidationIssue("description", f"Potentially unsafe wording requires rejection: {term}."))
        for term in self.REVIEW_TERMS:
            if term in combined:
                issues.append(ValidationIssue("description", f"Potentially discriminatory wording requires editorial review: {term}.", False))
        return issues

    @staticmethod
    def _word_count(value: str) -> int:
        return len(re.findall(r"\b[\w’'-]+\b", value, flags=re.UNICODE))

    @staticmethod
    def _looks_meaningless(value: str) -> bool:
        letters = re.sub(r"[^a-z]", "", value.casefold())
        if not letters:
            return True
        vowels = sum(letter in "aeiouy" for letter in letters)
        return len(letters) >= 10 and vowels / len(letters) < 0.12

    @staticmethod
    def _safe_https_url(value: str) -> bool:
        parsed = urlsplit(value.strip())
        return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username
