from __future__ import annotations

from collections import defaultdict
from datetime import date

from .config import JobsPublication
from .models import Vacancy, VacancyStatus
from .rendering import format_date, tracked_apply_url


def weekly_vacancy_list(
    vacancies: list[Vacancy], publication: JobsPublication, *, today: date | None = None
) -> str:
    current = (today or date.today()).isoformat()
    live = [
        item for item in vacancies
        if item.status in {VacancyStatus.APPROVED.value, VacancyStatus.SENT_TO_METRICOOL.value}
        and (not item.closing_date or item.closing_date >= current)
    ]
    grouped: dict[str, list[Vacancy]] = defaultdict(list)
    for vacancy in live:
        grouped[vacancy.area or "Other areas"].append(vacancy)
    lines = [f"THIS WEEK'S VACANCIES — {publication.page_name}", ""]
    for area in sorted(grouped, key=str.casefold):
        lines.extend((f"📍 {area}", ""))
        for vacancy in sorted(grouped[area], key=lambda item: (item.closing_date, item.job_title.casefold())):
            lines.extend((
                f"• {vacancy.job_title} — {vacancy.employer_name}",
                f"  {vacancy.salary_text} • {vacancy.contract_type}",
                f"  Closes: {format_date(vacancy.closing_date)}",
                f"  Apply: {tracked_apply_url(vacancy, publication)}",
                "",
            ))
    if not live:
        lines.append("No current vacancies are available this week.")
    lines.append("Applications are made directly to each employer.")
    return "\n".join(lines).strip()
