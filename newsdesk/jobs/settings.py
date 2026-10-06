from __future__ import annotations

import json
import os
from pathlib import Path

from newsdesk.social.store import _atomic_json, _protect, _unprotect


class JobsSettingsStore:
    def __init__(self, path=None):
        self.path = Path(path or Path("data") / "jobs_settings.json")

    def load(self):
        result = {
            "api_url": os.environ.get("JOBS_API_URL", ""),
            "api_token": os.environ.get("JOBS_ADMIN_TOKEN", ""),
            "publication_key": "devour_jobs_lincolnshire",
            "editor_name": "NewsDesk editor",
        }
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for key in ("api_url", "publication_key", "editor_name"):
                result[key] = str(data.get(key) or result[key]).strip()
            result["api_token"] = _unprotect(str(data.get("protected_api_token") or "")) or result["api_token"]
        except (OSError, ValueError, TypeError):
            pass
        return result

    def save(self, values):
        _atomic_json(self.path, {
            "schema_version": 1,
            "api_url": str(values.get("api_url") or "").strip().rstrip("/"),
            "publication_key": str(values.get("publication_key") or "devour_jobs_lincolnshire").strip(),
            "editor_name": str(values.get("editor_name") or "NewsDesk editor").strip(),
            "protected_api_token": _protect(str(values.get("api_token") or "").strip()),
        })
