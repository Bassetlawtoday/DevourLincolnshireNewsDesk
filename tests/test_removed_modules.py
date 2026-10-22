from __future__ import annotations

import ast
from pathlib import Path

from newsdesk.dashboard.registry import CARD_MODULE_KEYS, MODULE_NAMES
from newsdesk.dashboard.state_store import DEFAULT_STATE
from newsdesk.updates.store import ELIGIBLE_MODULES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOVED = {"fire", "planning"}


def _function_string_constants(path: Path, function_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return {
                value.value
                for value in ast.walk(node)
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            }
    raise AssertionError(f"Function not found: {function_name}")


def test_removed_modules_are_not_registered_or_scheduled():
    assert REMOVED.isdisjoint(MODULE_NAMES)
    assert REMOVED.isdisjoint(CARD_MODULE_KEYS)
    policies = DEFAULT_STATE["scheduler"]["module_policies"]
    assert REMOVED.isdisjoint(policies)


def test_removed_modules_are_not_eligible_for_updates():
    assert "fire" not in ELIGIBLE_MODULES
    assert "planning" not in ELIGIBLE_MODULES


def test_refresh_all_cannot_start_removed_modules():
    constants = _function_string_constants(
        PROJECT_ROOT / "modules" / "dashboard.py", "refresh_all"
    )
    assert REMOVED.isdisjoint(constants)


def test_refresh_coordinator_has_no_removed_collectors():
    source = (
        PROJECT_ROOT / "newsdesk" / "dashboard" / "refresh_coordinator.py"
    ).read_text(encoding="utf-8")
    assert '"planning": self._collect_planning' not in source
    assert '"fire": self._collect_fire' not in source
    assert "Module is not active" in source


def test_updates_ui_has_no_fire_filter():
    assert not (PROJECT_ROOT / "modules" / "updates_desk.py").exists()
