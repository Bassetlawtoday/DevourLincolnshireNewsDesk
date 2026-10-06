from __future__ import annotations

from datetime import date
from urllib.parse import quote

from .config import JobsPublication
from .models import Vacancy


def tracked_apply_url(vacancy: Vacancy, publication: JobsPublication) -> str:
    return f"{publication.apply_base_url}/{quote(vacancy.apply_token, safe='')}"


def facebook_post(vacancy: Vacancy, publication: JobsPublication) -> str:
    """Create consistent factual copy using only submitted vacancy fields."""
    positions = f" • {vacancy.positions} positions" if vacancy.positions > 1 else ""
    benefits = f"\n\nBenefits\n{vacancy.benefits.strip()}" if vacancy.benefits.strip() else ""
    requirements = f"\n\nWhat the employer is looking for\n{vacancy.requirements.strip()}" if vacancy.requirements.strip() else ""
    return (
        f"💼 JOB VACANCY — {vacancy.job_title.strip()}\n"
        f"📍 {vacancy.area.strip()} — {vacancy.location_detail.strip()}\n\n"
        f"Employer: {vacancy.employer_name.strip()}\n"
        f"Pay: {vacancy.salary_text.strip()}\n"
        f"Hours: {vacancy.hours_text.strip()}\n"
        f"Contract: {vacancy.contract_type.strip()} • {vacancy.workplace_type.strip()}{positions}\n\n"
        f"{vacancy.description.strip()}"
        f"{requirements}{benefits}\n\n"
        f"Closing date: {format_date(vacancy.closing_date)}\n"
        f"Apply now: {tracked_apply_url(vacancy, publication)}\n\n"
        "Advertisement submitted by the employer. Applications are made directly to the employer."
    )


def format_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d %B %Y")
    except ValueError:
        return value
