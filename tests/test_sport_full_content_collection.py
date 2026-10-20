from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from newsdesk.services.sport_collection import SportCollectionService
from newsdesk.story import Story


class _Engine:
    def process(self, _story):
        return SimpleNamespace()


class _Scraper:
    def __init__(self, story):
        self.story = story
        self.engine = _Engine()
        self.last_report = None

    def get_stories(self, **_kwargs):
        return [self.story]

    def close(self):
        pass


class _Images:
    def get(self, url, **_kwargs):
        return SimpleNamespace(
            source_url=url,
            local_path="",
            content_type="image/jpeg",
            width=0,
            height=0,
            file_size=0,
            cached=False,
            is_fallback=False,
            error="",
        )


class _Articles:
    def __init__(self, **_kwargs):
        pass

    def needs_enrichment(self, story):
        return story.extras.get("article_content_status") != "complete"

    def enrich(self, story):
        story.body = ("Verified full club article paragraph. " * 12).strip()
        story.extras["article_content_status"] = "complete"


def test_story_with_listing_image_still_gets_full_article(monkeypatch):
    story = Story(
        title="Club report",
        summary="Short listing teaser.",
        body="Short listing teaser.",
        source="Official Club",
        url="https://club.example/news/report",
        published=datetime.now(timezone.utc).isoformat(),
        image_url="https://club.example/report.jpg",
        extras={"article_content_status": "feed"},
    )
    monkeypatch.setattr(
        "newsdesk.services.sport_collection.SportArticleService", _Articles
    )
    result = SportCollectionService(
        scraper_factory=lambda: _Scraper(story),
        image_service_factory=lambda: _Images(),
    ).collect()

    assert result.stories[0].extras["article_content_status"] == "complete"
    assert len(result.stories[0].body) > len(result.stories[0].summary) + 40


def test_generated_placeholder_url_is_rejected():
    assert SportCollectionService._is_placeholder_image(
        "https://cdn.example/images/placeholder/generated.jpg"
    )
    assert not SportCollectionService._is_placeholder_image(
        "https://cdn.example/images/match-report.jpg"
    )
