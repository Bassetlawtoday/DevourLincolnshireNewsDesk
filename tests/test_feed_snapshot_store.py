from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from newsdesk.dashboard.result_repository import DashboardResultRepository
from newsdesk.publish_result import PublishResult
from newsdesk.story import Story


class FeedSnapshotTests(unittest.TestCase):
    def test_round_trip_restores_story_and_publish_result_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            story = Story(title="Saved story", body="Complete copy", url="https://example.test/story")
            result = PublishResult(website="Website copy", facebook="Facebook copy")
            first = DashboardResultRepository(path)
            completed = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
            first.set_result("fire", {"stories": [story], "publish_results": {id(story): result}, "errors": []}, completed)
            restored = DashboardResultRepository(path).get_result("fire")
            self.assertIsNotNone(restored)
            saved_story = restored.payload["stories"][0]
            self.assertEqual(saved_story.title, "Saved story")
            self.assertEqual(restored.payload["publish_results"][id(saved_story)].facebook, "Facebook copy")
            self.assertEqual(restored.completed_at, completed)

    def test_corrupt_primary_falls_back_to_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            repository = DashboardResultRepository(path)
            first = Story(title="First", body="Body")
            second = Story(title="Second", body="Body")
            now = datetime.now(timezone.utc)
            repository.set_result("sport", {"stories": [first]}, now)
            repository.set_result("sport", {"stories": [second]}, now)
            (path / "sport.json").write_text("not json", encoding="utf-8")
            restored = DashboardResultRepository(path).get_result("sport")
            self.assertEqual(restored.payload["stories"][0].title, "First")

    def test_unpersisted_modules_do_not_write_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            DashboardResultRepository(path).set_result("events", {"stories": []}, datetime.now(timezone.utc))
            self.assertEqual(list(path.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
