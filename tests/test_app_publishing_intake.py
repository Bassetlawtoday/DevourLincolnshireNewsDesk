"""App Publishing intake tests, independent of Social Desk."""
from types import SimpleNamespace

from newsdesk.app_publishing.intake import stage_app_story, story_identity
from newsdesk.app_publishing.store import AppArticleStore


def _story(**changes):
    values = {
        "story_id": "council:42",
        "url": "https://example.org/42",
        "title": "Original headline",
        "body": "A complete factual report about local council activity. " * 8,
        "summary": "Short teaser",
        "source": "Council",
        "image_url": "",
        "image_credit": "",
        "extras": {},
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_verified_council_story_is_staged(tmp_path):
    store = AppArticleStore(tmp_path / "app.json")
    article, created = stage_app_story(_story(), module_key="council", store=store)
    assert created
    assert article.title == "Original headline"
    assert len(store.load()) == 1


def test_changed_headline_does_not_duplicate_or_overwrite_editor(tmp_path):
    store = AppArticleStore(tmp_path / "app.json")
    first, _ = stage_app_story(_story(), module_key="council", store=store)
    first.body = "Editor approved text"
    store.upsert(first)
    second, created = stage_app_story(
        _story(title="Corrected source headline"), module_key="council", store=store
    )
    assert not created
    assert second.body == "Editor approved text"
    assert len(store.load()) == 1


def test_summary_only_story_is_not_staged(tmp_path):
    store = AppArticleStore(tmp_path / "app.json")
    article, created = stage_app_story(
        _story(body="Short teaser", summary="Short teaser"),
        module_key="council", store=store,
    )
    assert article is None
    assert not created
    assert store.load() == []


def test_ldrs_requires_detail_complete(tmp_path):
    store = AppArticleStore(tmp_path / "app.json")
    article, created = stage_app_story(
        _story(extras={}), module_key="content", store=store
    )
    assert article is None
    assert not created


def test_identity_ignores_source_headline_edits():
    assert story_identity(_story(), "council") == story_identity(
        _story(title="Corrected headline"), "council"
    )


def test_fire_content_is_excluded(tmp_path):
    store = AppArticleStore(tmp_path / "app.json")
    article, created = stage_app_story(_story(), module_key="fire", store=store)
    assert article is None
    assert not created
    assert store.load() == []
