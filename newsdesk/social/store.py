"""Atomic local storage for Social Desk drafts and non-secret settings."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4


SOCIAL_DIR = Path("data") / "social"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _protect(value: str) -> str:
    if not value:
        return ""
    if os.name != "nt":
        raise RuntimeError("Persistent API-token storage is available on Windows only.")
    raw = value.encode("utf-8")
    source = _Blob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
    result = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        raise ctypes.WinError()
    try:
        return base64.b64encode(ctypes.string_at(result.pbData, result.cbData)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


def _unprotect(value: str) -> str:
    if not value:
        return ""
    if os.name != "nt":
        return os.environ.get("METRICOOL_API_TOKEN", "")
    raw = base64.b64decode(value)
    source = _Blob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
    result = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


@dataclass(slots=True)
class SocialDraft:
    draft_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    text: str = ""
    source_url: str = ""
    internal_source_url: str = ""
    include_source_url: bool = True
    image_url: str = ""
    local_image_path: str = ""
    image_caption: str = ""
    image_credit: str = ""
    image_rights_status: str = "no image"
    source_kind: str = "blank"
    providers: list[str] = field(default_factory=list)
    important: bool = False
    instagram_hashtags: str = ""
    bluesky_text: str = ""
    bluesky_metricool_id: str = ""
    publication_datetime: str = ""
    timezone: str = "Europe/London"
    status: str = "local draft"
    metricool_id: str = ""
    # Stable collector identity used to prevent repeat staging across refreshes.
    source_identity: str = ""
    # Retained for backwards compatibility with drafts created by Updates Desk.
    origin_updates_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SocialDraft":
        allowed = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in allowed})


class SocialDraftStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or SOCIAL_DIR / "drafts.json"

    def load(self) -> list[SocialDraft]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return [SocialDraft.from_dict(item) for item in payload.get("drafts", [])]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def save(self, drafts: list[SocialDraft]) -> None:
        _atomic_json(self.path, {"schema_version": 2, "drafts": [asdict(item) for item in drafts]})

    def purge_older_than(self, days: int = 7, *, now: datetime | None = None) -> int:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = current - timedelta(days=days)
        drafts = self.load()
        kept = []
        for draft in drafts:
            try:
                stamp = datetime.fromisoformat(str(draft.created_at).replace("Z", "+00:00"))
                stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
            except (TypeError, ValueError):
                stamp = current
            if stamp >= cutoff:
                kept.append(draft)
        removed = len(drafts) - len(kept)
        if removed:
            self.save(kept)
        return removed

    @staticmethod
    def normalise_url(value: str) -> str:
        return str(value or "").strip().rstrip("/").casefold()

    def find_by_source_identity(self, drafts: list[SocialDraft], identity: str) -> SocialDraft | None:
        wanted = str(identity or "").strip().casefold()
        if not wanted:
            return None
        return next(
            (item for item in drafts if str(item.source_identity or "").strip().casefold() == wanted),
            None,
        )

    def find_by_source_url(self, drafts: list[SocialDraft], source_url: str) -> SocialDraft | None:
        wanted = self.normalise_url(source_url)
        if not wanted:
            return None
        return next(
            (
                item for item in drafts
                if wanted in {
                    self.normalise_url(item.source_url),
                    self.normalise_url(item.internal_source_url),
                }
            ),
            None,
        )


class SocialHandoffStore:
    """Content-free record of stories already handed to Social Desk."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or SOCIAL_DIR / "handoffs.json"

    def load(self) -> dict[str, dict[str, str]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            rows = payload.get("handoffs", {})
            return rows if isinstance(rows, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def contains(self, identity: str) -> bool:
        return bool(identity and identity.casefold() in self.load())

    def mark(self, identity: str, module_key: str) -> None:
        key = str(identity or "").strip().casefold()
        if not key:
            return
        rows = self.load()
        rows[key] = {
            "module_key": str(module_key or "").strip().casefold(),
            "staged_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_json(self.path, {"schema_version": 1, "handoffs": rows})


class SocialSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or SOCIAL_DIR / "metricool.json"

    def load(self) -> dict[str, str]:
        result = {"user_id": "", "blog_id": "", "brand_name": "", "timezone": "Europe/London", "token": "", "verified_at": "", "connected_networks": ""}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for key in ("user_id", "blog_id", "brand_name", "timezone", "verified_at", "connected_networks"):
                result[key] = str(data.get(key) or result[key])
            result["token"] = _unprotect(str(data.get("protected_token") or ""))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            result["token"] = os.environ.get("METRICOOL_API_TOKEN", "")
        return result

    def save(self, settings: dict[str, str]) -> None:
        payload = {
            "schema_version": 2,
            "user_id": str(settings.get("user_id") or "").strip(),
            "blog_id": str(settings.get("blog_id") or "").strip(),
            "brand_name": str(settings.get("brand_name") or "").strip(),
            "timezone": str(settings.get("timezone") or "Europe/London").strip(),
            "verified_at": str(settings.get("verified_at") or "").strip(),
            "connected_networks": str(settings.get("connected_networks") or "").strip(),
            "protected_token": _protect(str(settings.get("token") or "").strip()),
        }
        _atomic_json(self.path, payload)
