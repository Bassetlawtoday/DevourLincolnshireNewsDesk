from __future__ import annotations

from pathlib import Path

from modules.dashboard import Dashboard


class _Status:
    def __init__(self):
        self.values = {}

    def configure(self, **values):
        self.values.update(values)


def _dashboard_shell():
    dashboard = Dashboard.__new__(Dashboard)
    dashboard._closing = False
    dashboard._refresh_all_running = False
    dashboard._refresh_all_pending_keys = []
    dashboard._run_results = {}
    dashboard.refresh_all_button = _Status()
    dashboard.dashboard_status_label = _Status()
    return dashboard


def test_refresh_all_starts_ldrs_before_other_collectors():
    dashboard = _dashboard_shell()
    started = []
    dashboard._start_refresh = lambda key, **options: started.append((key, options))

    dashboard.refresh_all()

    assert started == [("content", {"part_of_batch": True})]
    assert dashboard._refresh_all_pending_keys == [
        "government", "council", "police", "sport"
    ]
    assert dashboard.refresh_all_button.values["state"] == "disabled"
    assert "Local Democracy" in dashboard.dashboard_status_label.values["text"]


def test_remaining_collectors_start_only_after_ldrs_finishes():
    dashboard = _dashboard_shell()
    dashboard._refresh_all_running = True
    dashboard._refresh_all_pending_keys = [
        "government", "council", "police", "sport"
    ]
    started = []
    dashboard._start_refresh = lambda key, **options: started.append((key, options))

    dashboard._start_refresh_all_followups()

    assert [key for key, _options in started] == [
        "government", "council", "police", "sport"
    ]
    assert all(options == {"part_of_batch": True} for _key, options in started)
    assert dashboard._refresh_all_pending_keys == []


def test_dashboard_ldrs_refresh_uses_module_scope():
    source = Path("newsdesk/dashboard/refresh_coordinator.py").read_text(encoding="utf-8")
    assert 'load_api_key, load_settings' in source
    assert 'scope = str(settings.get("default_scope") or "Latest 500").strip()' in source
    assert "collect_listings(limit=listing_limit)" in source
    assert '"scope": scope' in source
    assert 'collect_listings(limit=100)' not in source


def test_dashboard_stores_all_ldrs_listings_before_bounded_local_details():
    source = Path("newsdesk/dashboard/refresh_coordinator.py").read_text(encoding="utf-8")
    store_all = source.index("stored = store.upsert_many(rows)")
    local_filter = source.index("local_listings = [")
    detail_loop = source.index("for listing in local_listings:")
    detail_limit = source.index("if detail_attempts >= LDRS_DETAIL_LIMIT_PER_REFRESH:")
    assert store_all < local_filter < detail_loop < detail_limit
    assert "_is_lincolnshire_record(listing)" in source
    assert "for listing in rows:\n                    article_id" not in source
