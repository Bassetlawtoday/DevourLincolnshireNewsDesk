import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from newsdesk.story import Story
from newsdesk.updates.store import STATUS_METRICOOL, STATUS_NEW, STATUS_SOCIAL, UpdatesStore
from newsdesk.updates.content_gate import has_verified_full_content, is_materially_full


class Draft:
    origin_updates_id = ""
    metricool_id = ""
    status = ""


class UpdatesStoreTests(unittest.TestCase):
    def story(self, suffix="1"):
        return Story(story_id=f"police:{suffix}", title=f"Story {suffix}", body="Copy", source="Police", url=f"https://example.test/{suffix}")

    def test_planning_is_excluded(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            self.assertEqual(store.ingest("planning", [self.story()]), 0)
            self.assertEqual(store.summary()["total"], 0)

    def test_duplicate_never_reenters_after_delete(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            self.assertEqual(store.ingest("police", [self.story()]), 1)
            item = store.list_items()[0]
            store.delete(item.item_id)
            self.assertEqual(store.ingest("police", [self.story()]), 0)
            self.assertEqual(store.list_items(), [])

    def test_social_and_metricool_lifecycle(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            store.ingest("police", [self.story()])
            item = store.list_items()[0]
            self.assertEqual(item.status, STATUS_NEW)
            store.mark_social(item.item_id, "draft-1")
            self.assertEqual(store.list_items()[0].status, STATUS_SOCIAL)
            with self.assertRaises(ValueError):
                store.mark_social(item.item_id, "draft-2")
            store.mark_metricool(item.item_id, "metricool-1")
            updated = store.list_items()[0]
            self.assertEqual(updated.status, STATUS_METRICOOL)
            self.assertEqual(updated.metricool_id, "metricool-1")

    def test_module_names_do_not_collide(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            story = self.story()
            self.assertEqual(store.ingest("police", [story]), 1)
            self.assertEqual(store.ingest("fire", [story]), 1)
            self.assertEqual(store.summary()["total"], 2)

    def test_unsent_story_is_refreshed_but_not_reinserted(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            store.ingest("police", [self.story()])
            changed = self.story(); changed.title = "Revised source title"
            self.assertEqual(store.ingest("police", [changed]), 0)
            self.assertEqual(store.list_items()[0].title, "Revised source title")

    def test_reconcile_metricool_success(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            store.ingest("events", [self.story()])
            item = store.list_items()[0]
            store.mark_social(item.item_id, "draft-1")
            draft = Draft(); draft.origin_updates_id = item.item_id; draft.metricool_id = "m-9"; draft.status = "Sent to Metricool as draft"
            store.reconcile_social_drafts([draft])
            self.assertEqual(store.list_items()[0].status, STATUS_METRICOOL)

    def test_set_current_as_baseline_keeps_seen_identity(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            store.ingest("police", [self.story()])
            self.assertEqual(store.set_current_as_baseline(), 1)
            self.assertEqual(store.list_items(), [])
            self.assertEqual(store.ingest("police", [self.story()]), 0)

    def test_full_story_snapshot_can_be_replaced(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            story = self.story(); store.ingest("police", [story])
            item = store.list_items()[0]
            story.body = "Complete article copy"; story.image_url = "https://example.test/image.jpg"
            store.update_story(item.item_id, story)
            updated = store.list_items()[0]
            self.assertEqual(updated.story.body, "Complete article copy")
            self.assertEqual(updated.story.image_url, "https://example.test/image.jpg")

    def test_nested_datetime_is_serialized_for_police_story(self):
        with TemporaryDirectory() as directory:
            store = UpdatesStore(Path(directory) / "updates.sqlite")
            story = self.story()
            story.extras["incident"] = {
                "updated": datetime(2026, 9, 20, 9, 4, tzinfo=timezone.utc)
            }
            self.assertEqual(store.ingest("police", [story]), 1)
            self.assertEqual(
                store.list_items()[0].story.extras["incident"]["updated"],
                "2026-09-20T09:04:00+00:00",
            )

    def test_feed_teaser_and_image_are_not_full_content(self):
        story = self.story()
        story.summary = "A short feed teaser."
        story.body = story.summary
        story.image_url = "https://example.test/photo.jpg"
        story.extras["article_content_status"] = "complete"
        self.assertFalse(is_materially_full(story))
        self.assertFalse(has_verified_full_content("sport", story))

    def test_substantive_sport_article_passes_gate(self):
        story = self.story()
        story.summary = "A short feed teaser."
        story.body = " ".join(["Complete verified article paragraph."] * 12)
        story.extras["article_content_status"] = "complete"
        self.assertTrue(has_verified_full_content("sport", story))


if __name__ == "__main__":
    unittest.main()
