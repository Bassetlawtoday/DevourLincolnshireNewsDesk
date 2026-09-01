"""Static registry for NewsDesk Pro Home module orchestration metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DashboardModuleDefinition:
    key: str
    display_name: str
    workload: str
    show_card: bool = True
    planning_special: bool = False
    supports_repository_payload: bool = True
    collector_key: str = ""
    open_handler: str = ""
    count_adapter: str = "collected_count"
    default_schedule: str = "Every 60 minutes"


MODULE_DEFINITIONS = (
    DashboardModuleDefinition(
        "planning", "Planning Intelligence", "heavy", planning_special=True
    ),
    DashboardModuleDefinition("police", "Police Intelligence", "heavy"),
    DashboardModuleDefinition("fire", "Fire Intelligence", "light"),
    DashboardModuleDefinition("sport", "Sport Intelligence", "heavy"),
    DashboardModuleDefinition(
        "council",
        "Council",
        "light",
        collector_key="council",
        open_handler="open_council",
    ),
    DashboardModuleDefinition(
        "government",
        "Government / National Announcements",
        "light",
        show_card=False,
    ),
    DashboardModuleDefinition(
        "events", "Events Intelligence", "heavy", show_card=False,
        default_schedule="Every 12 hours",
    ),
    DashboardModuleDefinition(
        "content", "Local Democracy Intelligence", "heavy", show_card=False,
        default_schedule="Every 60 minutes",
    ),
)


def _build_registry(
    definitions: tuple[DashboardModuleDefinition, ...],
) -> dict[str, DashboardModuleDefinition]:
    registry: dict[str, DashboardModuleDefinition] = {}
    for definition in definitions:
        if not definition.key or definition.key in registry:
            raise ValueError(f"Duplicate or empty dashboard module key: {definition.key!r}")
        if definition.workload not in {"heavy", "light"}:
            raise ValueError(f"Invalid workload for {definition.key!r}")
        registry[definition.key] = definition
    return registry


MODULE_REGISTRY = _build_registry(MODULE_DEFINITIONS)
MODULE_NAMES = {
    key: definition.display_name for key, definition in MODULE_REGISTRY.items()
}
CARD_MODULE_KEYS = tuple(
    definition.key for definition in MODULE_DEFINITIONS if definition.show_card
)
HEAVY_MODULE_KEYS = frozenset(
    definition.key
    for definition in MODULE_DEFINITIONS
    if definition.workload == "heavy"
)


def get_module_definition(module_key: str) -> DashboardModuleDefinition:
    return MODULE_REGISTRY[module_key]
