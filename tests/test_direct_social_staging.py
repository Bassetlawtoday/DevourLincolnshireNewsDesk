from __future__ import annotations

from pathlib import Path

from newsdesk.social.selection import stage_story_for_social_desk
from newsdesk.social.store import SocialDraftStore
from newsdesk.story import Story


def _story(**overrides):
    values = {
        "story_id": "council:1",
        "title": "Council update",
        "summary": "A sufficiently useful council update for editorial review.",
        "body": "A sufficiently useful council update for editorial review.",
        "source": "Example Council",
        "url": "https://example.test/news/1",
        "published": "2026-10-19T10:00:00+00:00",
        "image_url": "",
        "image_credit": "",
    }
    values.update(overrides)
    return Story(**values)


def test_direct_staging_deduplicates_and_preserves_editor_changes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    draft, created = stage_story_for_social_desk(
        _story(), module_key="council"
    )
    assert created is True
    draft.text = "Edited by the newsroom"
    store = SocialDraftStore()
    store.save([draft])

    existing, created_again = stage_story_for_social_desk(
        _story(body="Collector replacement text"), module_key="council"
    )
    assert created_again is False
    assert existing.text == "Edited by the newsroom"
    assert len(store.load()) == 1


def test_missing_image_credit_does_not_block_story_staging(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    draft, created = stage_story_for_social_desk(
        _story(image_url="https://example.test/photo.jpg"),
        module_key="council",
    )
    assert created is True
    assert draft.image_url == ""
    assert draft.image_credit == ""
    assert draft.image_rights_status == "no image"


def test_ldrs_staging_keeps_provenance_private_and_byline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    story = _story(
        story_id="content:99",
        title="Local democracy report",
        url="https://ldrs.org.uk/article/99",
        author="Reporter Name",
        body=("Full verified reporting sentence. " * 10).strip(),
        summary="Full verified reporting sentence.",
        extras={"detail_complete": True},
    )
    draft, created = stage_story_for_social_desk(story, module_key="content")
    assert created is True
    assert draft.source_url == ""
    assert draft.internal_source_url == story.url
    assert draft.include_source_url is False
    assert draft.text.startswith("By: Reporter Name, LDRS.")
