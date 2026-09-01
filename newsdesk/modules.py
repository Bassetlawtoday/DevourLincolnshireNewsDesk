"""
NewsDesk module registry.

This file is the single source of truth for the modules displayed on the
NewsDesk dashboard.  It deliberately returns the dictionary structure already
expected by the dashboard so existing callers do not need to change.
"""

from __future__ import annotations

from collections.abc import Callable

from modules.fire import open_fire
from modules.events import open_events
from modules.planning import open_planning
from modules.police import open_police

from newsdesk.module import NewsDeskModule


AVAILABLE = "AVAILABLE"
COMING_SOON = "COMING SOON"


def _available_module(
    *,
    module_id: str,
    title: str,
    icon: str,
    description: str,
    launcher: Callable[[], object],
) -> NewsDeskModule:
    """Build an enabled dashboard module."""

    return NewsDeskModule(
        module_id=module_id,
        title=title,
        icon=icon,
        description=description,
        status=AVAILABLE,
        enabled=True,
        launcher=launcher,
    )


def _coming_soon_module(
    *,
    module_id: str,
    title: str,
    icon: str,
    coming_soon: Callable[[str], object],
    description: str = "Coming soon.",
) -> NewsDeskModule:
    """Build a disabled module that uses the dashboard's placeholder action."""

    return NewsDeskModule(
        module_id=module_id,
        title=title,
        icon=icon,
        description=description,
        status=COMING_SOON,
        enabled=False,
        launcher=lambda title=title: coming_soon(title),
    )


def get_modules(master, coming_soon):
    """
    Return all dashboard modules in display order.

    Parameters are intentionally unchanged from the original public API:

    ``master``
        Parent window passed to modules that require it.

    ``coming_soon``
        Callback used by unavailable dashboard modules.
    """

    modules = (
        _available_module(
            module_id="planning",
            title="Planning Intelligence",
            icon="🏗️",
            description=(
                "Download, analyse and score planning applications ready "
                "for publication."
            ),
            launcher=open_planning,
        ),
        _available_module(
            module_id="police",
            title="Police Intelligence",
            icon="👮",
            description=(
                "Collect, analyse and prepare Nottinghamshire Police "
                "stories for publication."
            ),
            launcher=lambda: open_police(master),
        ),
        _available_module(
            module_id="fire",
            title="Fire Intelligence",
            icon="🚒",
            description=(
                "Collect, analyse and prepare Nottinghamshire Fire and "
                "Rescue Service stories for publication."
            ),
            launcher=lambda: open_fire(master),
        ),
        _coming_soon_module(
            module_id="council",
            title="Council Intelligence",
            icon="🏛️",
            coming_soon=coming_soon,
        ),
        _coming_soon_module(
            module_id="business",
            title="Business Intelligence",
            icon="💼",
            coming_soon=coming_soon,
        ),
        _available_module(
            module_id="events",
            title="Events Intelligence",
            icon="📅",
            description="Collect, search, review and prepare regional events for newsletters.",
            launcher=lambda: open_events(master),
        ),
        _coming_soon_module(
            module_id="sport",
            title="Sport Intelligence",
            icon="⚽",
            coming_soon=coming_soon,
        ),
        _coming_soon_module(
            module_id="settings",
            title="Settings",
            icon="⚙️",
            description="Application settings.",
            coming_soon=coming_soon,
        ),
    )

    return tuple(module.as_dashboard_item() for module in modules)