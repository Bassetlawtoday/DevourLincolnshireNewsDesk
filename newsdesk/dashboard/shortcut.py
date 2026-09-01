"""Pure shortcut command construction used by setup tooling and tests."""

from __future__ import annotations

from pathlib import Path


def executable_shortcut_details(executable: Path | str) -> dict[str, str]:
    target = Path(executable).resolve()
    return {
        "name": "NewsDesk Pro",
        "target": str(target),
        "arguments": "",
        "working_directory": str(target.parent),
        "icon": str(target),
    }


def development_shortcut_details(
    interpreter: Path | str,
    project_root: Path | str,
) -> dict[str, str]:
    python = Path(interpreter).resolve()
    root = Path(project_root).resolve()
    return {
        "name": "NewsDesk Pro (Development)",
        "target": str(python),
        "arguments": f'"{root / "app.py"}"',
        "working_directory": str(root),
        "icon": str(python),
    }
