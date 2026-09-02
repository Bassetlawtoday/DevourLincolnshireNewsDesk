from datetime import datetime, timezone

from newsdesk.services.fire_service import FireCollectionService
from newsdesk.sources.base_scraper import ScrapeResponse
from newsdesk.sources.fire_scraper import (
    FireScraper,
    HumbersideFireIncidentScraper,
    _parse_fire_publication_datetime,
)
from newsdesk.story import Story


def test_primary_source_is_lincolnshire_county_council():
    scraper = FireScraper()
    assert scraper.NEWS_URL == "https://www.lincolnshire.gov.uk/news"
    assert scraper.source_name == "Lincolnshire Fire and Rescue"
    assert scraper._is_article_url(
        "https://www.lincolnshire.gov.uk/news/article/2819/inspection-report"
    )
    assert not scraper._is_article_url(
        "https://www.lincolnshire.gov.uk/news"
    )


def test_ordinal_and_humberside_dates_are_supported():
    assert _parse_fire_publication_datetime("Published: 1st July 2026") == datetime(
        2026, 7, 1, tzinfo=timezone.utc
    )
    assert _parse_fire_publication_datetime("Mon 31 Aug 2026 23:33") == datetime(
        2026, 8, 31, 23, 33, tzinfo=timezone.utc
    )


def test_humberside_incidents_are_split_and_geographically_filtered():
    html = """
    <main>
      <h3>Brereton Avenue, Cleethorpes.</h3>
      <p>Small amount of rubbish on fire extinguished by firefighters.</p>
      <p>Date &amp; Time: Mon 31 Aug 2026 22:06 (No:021707)</p>
      <p>Incident Number: 021707</p>
      <p>Incident Type: FIRE SECONDARY</p>
      <h3>Monmouth Street, Hull.</h3>
      <p>Falls Team.</p>
      <p>Date &amp; Time: Mon 31 Aug 2026 22:05 (No:021706)</p>
      <p>Incident Number: 021706</p>
      <p>Incident Type: SPECIAL SERVICE MEDICAL</p>
    </main>
    """
    scraper = HumbersideFireIncidentScraper()
    stories = list(
        scraper.parse(
            ScrapeResponse(
                url=scraper.NEWS_URL,
                body=html,
                status_code=200,
            )
        )
    )
    assert len(stories) == 1
    story = stories[0]
    assert story.title == "Brereton Avenue, Cleethorpes."
    assert story.extras["incident_number"] == "021707"
    assert story.extras["incident_type"] == "FIRE SECONDARY"
    assert "Small amount of rubbish" in story.body


def test_cross_source_deduplication_keeps_distinct_incidents():
    first = Story(
        title="Cleethorpes incident",
        source="Humberside Fire and Rescue Service",
        url="https://example.test/incidents#incident-1",
        extras={"incident_number": "1"},
    )
    second = Story(
        title="Grimsby incident",
        source="Humberside Fire and Rescue Service",
        url="https://example.test/incidents#incident-2",
        extras={"incident_number": "2"},
    )
    assert FireCollectionService._deduplicate_stories([first, second]) == [first, second]
