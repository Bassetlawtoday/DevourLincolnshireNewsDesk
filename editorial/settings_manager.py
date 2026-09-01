"""Load and save NewsDesk editorial settings."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_ROOT / "data" / "editorial_settings.json"


class EditorialSettingsError(RuntimeError):
    """Raised when editorial settings cannot be loaded or saved."""


def load_editorial_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        raise EditorialSettingsError(
            f"Editorial settings file not found: {SETTINGS_PATH}"
        )

    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise EditorialSettingsError(
            f"Could not load editorial settings: {error}"
        ) from error

    required_sections = (
        "thresholds",
        "zones",
        "global_signals",
        "module_profiles",
    )

    missing = [
        name
        for name in required_sections
        if name not in settings
    ]

    if missing:
        raise EditorialSettingsError(
            "Editorial settings are missing: " + ", ".join(missing)
        )

    for profile_name, profile in settings["module_profiles"].items():
        thresholds = profile.get(
            "thresholds",
            settings["thresholds"],
        )

        required_thresholds = (
            "front_page",
            "high_priority",
            "newsworthy",
            "monitor",
        )

        missing_thresholds = [
            name
            for name in required_thresholds
            if name not in thresholds
        ]

        if missing_thresholds:
            raise EditorialSettingsError(
                f"Profile '{profile_name}' is missing thresholds: "
                + ", ".join(missing_thresholds)
            )

    return settings


def save_editorial_settings(settings: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = SETTINGS_PATH.with_suffix(".json.tmp")

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(settings, file, indent=4)
            file.write("\n")

        temporary_path.replace(SETTINGS_PATH)

    except OSError as error:
        raise EditorialSettingsError(
            f"Could not save editorial settings: {error}"
        ) from error


def get_settings_copy() -> dict[str, Any]:
    return deepcopy(load_editorial_settings())
