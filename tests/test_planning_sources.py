import json
import tempfile
import unittest
from pathlib import Path

from services.planning_sources import (
    enabled_idox_sources,
    load_planning_sources,
)


EXPECTED_AUTHORITIES = {
    "Boston Borough Council",
    "City of Lincoln Council",
    "East Lindsey District Council",
    "Lincolnshire County Council",
    "North East Lincolnshire Council",
    "North Kesteven District Council",
    "North Lincolnshire Council",
    "South Holland District Council",
    "South Kesteven District Council",
    "West Lindsey District Council",
}


class PlanningSourceTests(unittest.TestCase):
    def test_catalogue_covers_all_ten_lincolnshire_authorities(self):
        sources = load_planning_sources()
        authorities = {
            authority
            for source in sources
            for authority in source.authorities
        }

        self.assertEqual(authorities, EXPECTED_AUTHORITIES)
        self.assertEqual(len(sources), 9)

    def test_first_phase_has_five_idox_endpoints_covering_six_authorities(self):
        sources = enabled_idox_sources()
        authorities = {
            authority
            for source in sources
            for authority in source.authorities
        }

        self.assertEqual(len(sources), 5)
        self.assertEqual(
            authorities,
            {
                "Boston Borough Council",
                "City of Lincoln Council",
                "East Lindsey District Council",
                "North East Lincolnshire Council",
                "North Kesteven District Council",
                "South Kesteven District Council",
            },
        )
        self.assertTrue(
            all("/online-applications/" in source.weekly_url for source in sources)
        )

    def _write_config(self, payload):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "planning.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loader_rejects_duplicate_source_keys(self):
        path = self._write_config(
            {
                "version": 1,
                "sources": [
                    {
                        "key": "duplicate",
                        "name": "One",
                        "authorities": ["One Council"],
                        "platform": "idox_public_access",
                        "base_url": "https://one.example/online-applications/",
                        "enabled": True,
                    },
                    {
                        "key": "duplicate",
                        "name": "Two",
                        "authorities": ["Two Council"],
                        "platform": "idox_public_access",
                        "base_url": "https://two.example/online-applications/",
                        "enabled": True,
                    },
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "Duplicate planning source key"):
            load_planning_sources(path)

    def test_loader_rejects_non_https_sources(self):
        path = self._write_config(
            {
                "version": 1,
                "sources": [
                    {
                        "key": "unsafe",
                        "name": "Unsafe",
                        "authorities": ["Unsafe Council"],
                        "platform": "idox_public_access",
                        "base_url": "http://unsafe.example/online-applications/",
                        "enabled": True,
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            load_planning_sources(path)


if __name__ == "__main__":
    unittest.main()
