from __future__ import annotations

from pathlib import Path

from newsdesk.social.selection import stage_story_for_social_desk
from newsdesk.social.store import SocialDraftStore
from newsdesk.story import Story
from newsdesk.dashboard.refresh_coordinator import DashboardRefreshCoordinator
from newsdesk.dashboard.state_store import DashboardStateStore


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


def test_incomplete_sport_story_is_retried_after_full_content_arrives(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_store = DashboardStateStore(tmp_path / "dashboard.json")
    coordinator = DashboardRefreshCoordinator(state_store=state_store)
    incomplete = _story(
        story_id="sport:1",
        source="Official Club",
        summary="Short fixture teaser.",
        body="Short fixture teaser.",
        extras={"article_content_status": "feed"},
    )
    key = coordinator.item_keys("sport", {"stories": [incomplete]})[0]
    state = state_store.load()
    state["modules"]["sport"] = {"known_item_keys": ["existing-baseline"]}
    state_store.save(state)

    assert coordinator._stage_new_social_drafts(
        "sport", {"stories": [incomplete]}
    ) == 0
    assert key in state_store.load()["modules"]["sport"]["social_stage_pending_keys"]

    complete = _story(
        story_id="sport:1",
        source="Official Club",
        summary="Short fixture teaser.",
        body=("Verified full match report paragraph. " * 12).strip(),
        extras={"article_content_status": "complete"},
    )
    assert coordinator._stage_new_social_drafts(
        "sport", {"stories": [complete]}
    ) == 1
    assert state_store.load()["modules"]["sport"]["social_stage_pending_keys"] == []
