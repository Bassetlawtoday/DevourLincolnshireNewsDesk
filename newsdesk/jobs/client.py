from __future__ import annotations

import requests

from .models import Vacancy


class JobsApiClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def vacancies(self, publication_key: str, statuses=()) -> tuple[list[Vacancy], dict[str, int]]:
        response = requests.get(
            f"{self.base_url}/api/v1/vacancies",
            params={"publication": publication_key, "status": ",".join(statuses)},
            headers={"Authorization": f"Bearer {self.token}"}, timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        return [Vacancy.from_dict(row) for row in payload.get("vacancies", [])], payload.get("clicks", {})

    def action(self, vacancy_id: str, action: str, **payload) -> Vacancy:
        response = requests.post(
            f"{self.base_url}/api/v1/vacancies/{vacancy_id}/actions/{action}",
            json=payload, headers={"Authorization": f"Bearer {self.token}"}, timeout=25,
        )
        if response.status_code == 409:
            raise ValueError(response.json().get("error") or "The action could not be completed.")
        response.raise_for_status()
        return Vacancy.from_dict(response.json()["vacancy"])
