"""
Live test for the Nottinghamshire Police scraper.
"""

from newsdesk.sources.police_scraper import PoliceScraper


def main() -> None:
    scraper = PoliceScraper(
        limit=3,
        headless=False,
    )

    try:
        stories = scraper.fetch_latest_news()

        print()
        print(f"Collected {len(stories)} police stories.")
        print()

        for number, story in enumerate(stories, start=1):
            print(f"{number}. {story.title}")
            print(f"   Source: {story.source}")
            print(f"   Published: {story.published}")
            print(f"   URL: {story.url}")
            print(f"   Body characters: {len(story.body)}")
            print()

    finally:
        scraper.close()


if __name__ == "__main__":
    main()