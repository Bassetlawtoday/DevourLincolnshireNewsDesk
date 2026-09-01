"""Local, Git-safe settings and Windows-protected API-key storage."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "contentdesk"
SETTINGS_PATH = DATA_DIR / "settings.json"
KEY_PATH = DATA_DIR / "api-key.dpapi"
BASE_URL = "https://ldrs.org.uk"


class CredentialError(RuntimeError):
    """Raised when a locally protected API key cannot be stored or restored."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect_windows(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "NewsDesk Pro LDRS", None, None, None, 0,
        ctypes.byref(target),
    ):
        raise CredentialError("Windows could not protect the LDRS API key.")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)
        del source_buffer


def _unprotect_windows(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
    ):
        raise CredentialError("Windows could not unlock the saved LDRS API key.")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)
        del source_buffer


def save_api_key(value: str) -> None:
    key = str(value or "").strip()
    if not key:
        raise CredentialError("Enter the LDRS API key before saving.")
    if os.name != "nt":
        raise CredentialError("Secure API-key storage is available only on Windows.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    protected = _protect_windows(key.encode("utf-8"))
    KEY_PATH.write_bytes(base64.b64encode(protected))


def load_api_key() -> str:
    environment_key = str(os.environ.get("LDRS_API_KEY", "")).strip()
    if environment_key:
        return environment_key
    if not KEY_PATH.is_file():
        return ""
    if os.name != "nt":
        return ""
    try:
        protected = base64.b64decode(KEY_PATH.read_bytes(), validate=True)
        return _unprotect_windows(protected).decode("utf-8").strip()
    except (OSError, ValueError, UnicodeError) as exc:
        raise CredentialError("The saved LDRS API key could not be read.") from exc


def has_api_key() -> bool:
    try:
        return bool(load_api_key())
    except CredentialError:
        return False


def load_settings() -> dict:
    defaults = {"base_url": BASE_URL, "default_scope": "Latest 500"}
    if not SETTINGS_PATH.is_file():
        return defaults
    try:
        values = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return defaults
    if not isinstance(values, dict):
        return defaults
    defaults.update({key: value for key, value in values.items() if key in defaults})
    return defaults


def save_settings(values: dict) -> None:
    current = load_settings()
    current.update({key: value for key, value in values.items() if key in current})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
