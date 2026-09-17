"""Read-only Planning source catalogue for the specialist collectors."""

from __future__ import annotations

import json
from pathlib import Path

from modules.sport_source_manager import SportSourceManagerWindow


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "planning_websites.json"


class PlanningSourceManagerWindow(SportSourceManagerWindow):
    """Display the real Planning source catalogue and operational details."""

    def _planning_definitions(self):
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        definitions = []
        for source in payload.get("sources", []):
            definitions.append(
                {
                    "source_id": source.get("key", ""),
                    "name": source.get("name", "Planning source"),
                    "organisation": source.get("organisation", ""),
                    "listing_url": source.get("weekly_list_url")
                    or source.get("base_url", ""),
                    "sport": source.get("category", "Planning applications"),
                    "location": source.get("locality", "Lincolnshire"),
                    "tags": source.get("tags", []),
                    "max_stories": "All applications in the configured period",
                    "enabled": bool(source.get("enabled", True)),
                    "module_profile": "planning",
                    "managed_by": "core",
                    "protected": True,
                    "connection_status": (
                        "Configured and enabled"
                        if source.get("enabled", True)
                        else "Configured but disabled"
                    ),
                    "collection_method": source.get("collection_method", ""),
                    "search_period": source.get("search_period", ""),
                    "operational_note": source.get("transition_note", ""),
                    "authorities": source.get("authorities", []),
                }
            )
        return definitions

    def _reload_sources(self):
        self.definitions = self._planning_definitions()
        self._render_source_list()

    def _set_read_only(self, value):
        super()._set_read_only(value)
        if not value:
            return
        details = self.current_raw
        lines = [
            "This source is used by Planning's protected specialist collector.",
            "It is shown for visibility and cannot be edited or deleted.",
            "",
            f"Authorities: {', '.join(details.get('authorities', [])) or 'Not specified'}",
            f"Collection method: {details.get('collection_method') or 'Not specified'}",
            f"Search period: {details.get('search_period') or 'Not specified'}",
        ]
        if details.get("operational_note"):
            lines.append(f"Operational note: {details['operational_note']}")
        self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        self.results.insert("1.0", "\n".join(lines))
        self.results.configure(state="disabled")


SourceManagerWindow = PlanningSourceManagerWindow

