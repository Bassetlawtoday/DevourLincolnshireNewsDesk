from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "jobs.json"


@dataclass(frozen=True, slots=True)
class JobsPublication:
    key: str
    brand_name: str
    page_name: str
    form_title: str
    core_areas: tuple[str, ...]
    allow_outside_area: bool
    public_base_url: str
    apply_path: str
    timezone: str
    currency: str
    metricool_provider: str

    @property
    def apply_base_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/{self.apply_path.strip('/')}"


def load_publications(path: str | Path | None = None) -> dict[str, JobsPublication]:
    payload = json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    result: dict[str, JobsPublication] = {}
    for item in payload.get("publications", []):
        values = dict(item)
        local_override = os.environ.get("JOBS_PUBLIC_BASE_URL", "").strip()
        if local_override:
            values["public_base_url"] = local_override.rstrip("/")
        values["core_areas"] = tuple(values.get("core_areas") or ())
        publication = JobsPublication(**values)
        if not publication.key or publication.key in result:
            raise ValueError("Jobs publication keys must be non-empty and unique.")
        result[publication.key] = publication
    if not result:
        raise ValueError("At least one Jobs publication must be configured.")
    return result
