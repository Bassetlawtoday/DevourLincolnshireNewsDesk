from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "eventsdesk_source_scope", ROOT / "eventsdesk" / "source_scope.py"
)
assert _SPEC and _SPEC.loader
_SCOPE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SCOPE)
counties_for_area = _SCOPE.counties_for_area
event_is_allowed = _SCOPE.event_is_allowed
event_is_in_enabled_geography = _SCOPE.event_is_in_enabled_geography


class LincolnshireEventScopeTests(unittest.TestCase):
    def test_greater_lincolnshire_places_are_in_scope(self):
        for place in ("Lincoln", "Scunthorpe", "Grimsby", "Cleethorpes", "Stamford"):
            with self.subTest(place=place):
                self.assertEqual(counties_for_area(place), ("Lincolnshire",))

    def test_other_east_midlands_places_are_out_of_scope(self):
        for place in ("Nottingham", "Derby", "Leicester", "Northampton"):
            with self.subTest(place=place):
                self.assertEqual(counties_for_area(place), ())

    def test_fringe_sources_are_not_trusted(self):
        self.assertEqual(counties_for_area("Lincolnshire fringe"), ())

    def test_regional_event_needs_local_event_evidence(self):
        event = SimpleNamespace(
            county="", town="Grimsby", venue="Docks Academy", address="", postcode="",
        )
        self.assertTrue(event_is_in_enabled_geography(event, "East Midlands"))
        event.town = "Nottingham"
        event.venue = "Rock City"
        self.assertFalse(event_is_in_enabled_geography(event, "East Midlands"))

    def test_cinema_categories_are_excluded(self):
        for category in ("Film", "Cinema", "Movie", "Event Cinema"):
            with self.subTest(category=category):
                self.assertFalse(event_is_allowed(SimpleNamespace(category=category)))
        self.assertTrue(event_is_allowed(SimpleNamespace(category="Theatre")))

    def test_extension_registry_is_local_and_has_no_cinema_source(self):
        payload = json.loads(
            (ROOT / "eventsdesk" / "data" / "lincolnshire_sources.json").read_text(encoding="utf-8")
        )
        sources = payload["sources"]
        self.assertGreaterEqual(len(sources), 25)
        self.assertEqual(len({row["id"] for row in sources}), len(sources))
        self.assertTrue(all(counties_for_area(row["area"]) for row in sources))
        self.assertFalse(any("cinema" in row["type"].casefold() for row in sources))
        names = {row["name"] for row in sources}
        self.assertIn("Scunthorpe Theatres", names)
        self.assertIn("Grimsby Auditorium", names)
        self.assertIn("Lincolnshire Wildlife Trust", names)


if __name__ == "__main__":
    unittest.main()
