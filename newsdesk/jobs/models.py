from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class VacancyStatus(StrEnum):
    SUBMITTED = "submitted"
    NEEDS_CHANGES = "needs_changes"
    APPROVED = "approved"
    SENT_TO_METRICOOL = "sent_to_metricool"
    REJECTED = "rejected"
    EXPIRED = "expired"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Vacancy:
    vacancy_id: str = field(default_factory=lambda: uuid4().hex)
    publication_key: str = ""
    employer_name: str = ""
    employer_legal_name: str = ""
    employer_website: str = ""
    company_number: str = ""
    submitter_name: str = ""
    submitter_email: str = ""
    submitter_phone: str = ""
    submitter_authorised: bool = False
    job_title: str = ""
    area: str = ""
    location_detail: str = ""
    outside_core_area: bool = False
    salary_text: str = ""
    hours_text: str = ""
    contract_type: str = ""
    workplace_type: str = ""
    positions: int = 1
    description: str = ""
    requirements: str = ""
    benefits: str = ""
    application_url: str = ""
    application_email: str = ""
    closing_date: str = ""
    logo_url: str = ""
    genuine_vacancy_confirmed: bool = False
    equality_confirmed: bool = False
    terms_accepted: bool = False
    status: str = VacancyStatus.SUBMITTED.value
    apply_token: str = field(default_factory=lambda: uuid4().hex)
    metricool_id: str = ""
    editorial_note: str = ""
    submitted_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    approved_at: str = ""
    approved_by: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict) -> "Vacancy":
        allowed = cls.__dataclass_fields__
        return cls(**{key: value for key, value in values.items() if key in allowed})
