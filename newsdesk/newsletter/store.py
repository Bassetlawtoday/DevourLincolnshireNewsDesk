"""Versioned, atomic, recoverable storage for newsletter editions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .models import NewsletterEdition


class NewsletterStore:
    SCHEMA_VERSION = 1
    FORBIDDEN_KEYS = {
        "access_token",
        "admin_api_key",
        "api_key",
        "password",
        "secret",
        "token",
    }

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path("data") / "newsletter" / "editions.json")
        self.backup_path = self.path.with_suffix(".backup.json")
        self.recovered_from_backup = False

    def load(self) -> list[NewsletterEdition]:
        self.recovered_from_backup = False
        try:
            return self._read(self.path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            try:
                editions = self._read(self.backup_path)
                self.recovered_from_backup = True
                return editions
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                return []

    def save(self, editions: list[NewsletterEdition]) -> None:
        document = {
            "schema_version": self.SCHEMA_VERSION,
            "editions": [edition.to_dict() for edition in editions],
        }
        self._reject_secrets(document)
        encoded = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                shutil.copy2(self.path, self.backup_path)
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def _read(self, path: Path) -> list[NewsletterEdition]:
        document = json.loads(path.read_text(encoding="utf-8"))
        if int(document.get("schema_version", -1)) != self.SCHEMA_VERSION:
            raise ValueError("Unsupported newsletter schema.")
        editions = [
            NewsletterEdition.from_dict(item) for item in document.get("editions", [])
        ]
        identities: set[str] = set()
        for edition in editions:
            if edition.edition_id in identities:
                raise ValueError("Duplicate newsletter edition ID.")
            identities.add(edition.edition_id)
            item_identities = [item.source_identity for item in edition.items]
            if len(item_identities) != len(set(item_identities)):
                raise ValueError("Duplicate newsletter item identity.")
        return editions

    @classmethod
    def _reject_secrets(cls, value: Any, *, path: str = "document") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalised = str(key).strip().casefold()
                if normalised in cls.FORBIDDEN_KEYS:
                    raise ValueError(f"Newsletter storage cannot contain credentials ({path}.{key}).")
                cls._reject_secrets(item, path=f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                cls._reject_secrets(item, path=f"{path}[{index}]")
