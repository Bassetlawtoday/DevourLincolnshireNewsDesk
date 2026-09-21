import json
import unittest

from bs4 import BeautifulSoup

from newsdesk.sports.websites.generic_website_scraper import GenericWebsiteScraper
from newsdesk.sports.websites.source import WebsiteSource


class PitcheroCollectionTests(unittest.TestCase):
    def test_next_data_news_is_collected(self):
        source = WebsiteSource(
            name="Boston United",
            sport="Football",
            organisation="Boston United Football Club",
            listing_url="https://www.bostonunited.co.uk/news",
            location="Lincolnshire",
        )
        scraper = GenericWebsiteScraper(source)
        payload = {
            "props": {"initialReduxState": {"activityStream": {"messages": {
                "news-123": {
                    "type": "news", "article_id": 123,
                    "title": "United appoint new chief executive",
                    "tagline": "The club has confirmed its new appointment.",
                    "published": "2026-09-20T10:00:00+01:00",
                    "image": "https://img-res.pitchero.com/photo.jpg",
                    "author": {"name": "Club reporter"},
                },
                "match_report-99": {
                    "type": "match_report", "title": "Boston United win away",
                    "tagline": "A complete report from the club's latest fixture.",
                    "published": "2026-09-19T18:00:00+01:00",
                    "team_id": 24809,
                    "fixture": {"fixture_id": "1-19876643"},
                },
            }}}}
        }
        soup = BeautifulSoup(
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script>",
            "html.parser",
        )
        stories = scraper._stories_from_pitchero_page_data(
            soup, source.listing_url
        )
        self.assertEqual(len(stories), 2)
        self.assertEqual(stories[0].source, "Boston United")
        self.assertEqual(stories[0].author, "Club reporter")
        self.assertIn("/news/united-appoint-new-chief-executive-123.html", stories[0].url)
        self.assertEqual(
            stories[0].extras["collector_route"], "pitchero-next-data"
        )
        self.assertEqual(
            stories[1].url,
            "https://www.bostonunited.co.uk/teams/24809/match-centre/1-19876643/report",
        )


if __name__ == "__main__":
    unittest.main()
