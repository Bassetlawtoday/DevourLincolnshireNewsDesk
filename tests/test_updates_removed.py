from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_updates_desk_is_not_exposed_by_dashboard():
    source = (PROJECT_ROOT / "modules" / "dashboard.py").read_text(encoding="utf-8")
    assert "modules.updates_desk" not in source
    assert "_build_updates_card" not in source
    assert "_open_updates_desk" not in source


def test_refresh_coordinator_does_not_ingest_updates_queue():
    source = (
        PROJECT_ROOT / "newsdesk" / "dashboard" / "refresh_coordinator.py"
    ).read_text(encoding="utf-8")
    assert "UpdatesStore" not in source
    assert "stage_story_for_social_desk" in source
    assert '"stage_stories": stage_stories' in source


def test_ldrs_detail_is_required_before_direct_staging():
    source = (
        PROJECT_ROOT / "newsdesk" / "dashboard" / "refresh_coordinator.py"
    ).read_text(encoding="utf-8")
    assert "collector.fetch_detail(article_id)" in source
    assert 'has_verified_full_content("content", story)' in source
    assert "it was not staged" in source
