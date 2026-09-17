import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.models import PlanningApplication


class PlanningDatabaseTests(unittest.TestCase):
    def setUp(self):
        import database.database as planning_database

        self.database = planning_database
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.original_database = planning_database.DATABASE
        planning_database.DATABASE = Path(self.temporary.name) / "planning.db"
        self.addCleanup(self._restore_database_path)

    def _restore_database_path(self):
        self.database.DATABASE = self.original_database

    def test_same_reference_is_retained_for_two_authorities(self):
        self.database.create_database()
        first = PlanningApplication(
            reference="26/0001/FUL",
            planning_authority="City of Lincoln Council",
            planning_source_key="city_of_lincoln",
            proposal="First proposal",
        )
        second = PlanningApplication(
            reference="26/0001/FUL",
            planning_authority="South Kesteven District Council",
            planning_source_key="south_kesteven",
            proposal="Second proposal",
        )

        self.database.save_planning_application(first)
        self.database.save_planning_application(second)

        self.assertEqual(self.database.total_applications(), 2)

    def test_legacy_primary_key_schema_is_migrated_without_data_loss(self):
        connection = sqlite3.connect(self.database.DATABASE)
        connection.execute(
            "CREATE TABLE planning(reference TEXT PRIMARY KEY, proposal TEXT)"
        )
        connection.execute(
            "INSERT INTO planning(reference, proposal) VALUES(?, ?)",
            ("22/0001/FUL", "Legacy proposal"),
        )
        connection.commit()
        connection.close()

        self.database.create_database()

        connection = sqlite3.connect(self.database.DATABASE)
        columns = connection.execute("PRAGMA table_info(planning)").fetchall()
        row = connection.execute(
            "SELECT reference, planning_source_key, proposal FROM planning"
        ).fetchone()
        connection.close()

        primary_key_columns = [
            column[1]
            for column in sorted(columns, key=lambda column: column[5])
            if column[5]
        ]
        self.assertEqual(
            primary_key_columns,
            ["planning_source_key", "reference"],
        )
        self.assertEqual(row, ("22/0001/FUL", "legacy_bassetlaw", "Legacy proposal"))


if __name__ == "__main__":
    unittest.main()
