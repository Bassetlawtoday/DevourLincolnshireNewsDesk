"""Tests for isolated App Publishing draft storage."""
from types import SimpleNamespace

from newsdesk.app_publishing.store import AppArticleStore


def test_stage_and_reopen(tmp_path):
    store = AppArticleStore(tmp_path / "drafts.json")
    story = SimpleNamespace(
        title="Council update", body="Original reporting", summary="Teaser",
        source="Council", url="https://example.org/story", author="Reporter",
        image_url="", image_local_path="", image_caption="", image_credit="",
        category="Council",
    )
    article, created = store.stage_story(story, source_identity="council:123")
    assert created
    assert article.word_count == 2
    article.body = "Edited for the app"
    store.upsert(article)
    repeated, created = store.stage_story(story, source_identity="council:123")
    assert not created
    assert repeated.body == "Edited for the app"
    assert repeated.original_body == "Original reporting"


def test_distinct_sources_remain_distinct(tmp_path):
    store = AppArticleStore(tmp_path / "drafts.json")
    story = SimpleNamespace(title="News", body="Copy")
    store.stage_story(story, source_identity="police:1")
    store.stage_story(story, source_identity="council:1")
    assert len(store.load()) == 2


def test_missing_identity_is_rejected(tmp_path):
    store = AppArticleStore(tmp_path / "drafts.json")
    try:
        store.stage_story(SimpleNamespace(title="News"), source_identity="")
    except ValueError:
        pass
    else:
        raise AssertionError("Missing identity should be rejected")
