from __future__ import annotations

from contentdesk.collector import ContentExplorerCollector


class _Element:
    text = "Account Name   Log Out"


class _AuthenticatedDriver:
    current_url = "https://ldrs.org.uk/explorer/story"

    def __init__(self):
        self.get_calls = []

    def find_elements(self, *_args):
        return [_Element()]

    def get(self, url):
        self.get_calls.append(url)


def test_login_reuses_an_authenticated_browser_session():
    collector = ContentExplorerCollector("configured-key")
    driver = _AuthenticatedDriver()
    collector._driver = driver

    collector.login()

    assert driver.get_calls == []
