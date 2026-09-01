"""
NewsDesk module definition.

Defines the data structure used by the NewsDesk module registry.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class NewsDeskModule:
    """Represents a module shown on the NewsDesk dashboard."""

    module_id: str
    title: str
    icon: str
    description: str
    status: str
    enabled: bool
    launcher: Callable

    def as_dashboard_item(self) -> dict:
        """
        Returns the format currently expected by the dashboard.

        Keeping this method means the dashboard doesn't need to know
        anything about the underlying dataclass.
        """
        return {
            "id": self.module_id,
            "title": self.title,
            "icon": self.icon,
            "description": self.description,
            "status": self.status,
            "enabled": self.enabled,
            "command": self.launcher,
        }