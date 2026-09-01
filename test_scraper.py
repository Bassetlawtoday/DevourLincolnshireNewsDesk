from newsdesk.sources.base_scraper import BaseScraper, ScrapeResponse
from newsdesk.story import Story


class DemoScraper(BaseScraper):
    def parse(self, response: ScrapeResponse):
        return [
            Story(
                title="Police operation leads to arrests in Worksop",
                body=(
                    "Police officers carried out an operation in Worksop "
                    "following reports from members of the public. "
                    "Several arrests were made and enquiries remain ongoing."
                ),
                url="https://example.com/story",
            )
        ]


scraper = DemoScraper(
    source_name="Demo News",
    source_url="https://example.com",
)

response = ScrapeResponse(
    url="https://example.com",
    body="<html></html>",
    status_code=200,
)

stories = scraper._normalise_stories(
    scraper.parse(response)
)

print(stories[0].source)
print(stories[0].title)