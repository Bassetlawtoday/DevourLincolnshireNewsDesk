from datetime import datetime, timezone

from newsdesk.sources.council_scraper import CouncilSource, CouncilSourceScraper


SOURCE = CouncilSource(
    key="boston_borough_council",
    name="Boston Borough Council",
    url="https://www.boston.gov.uk/news/",
    detail_path_patterns=(r"^/article/\d+/",),
)


def test_boston_goss_listing_discovers_official_article():
    html = """
    <html><body>
      <div class="news-item">
        <h2><a href="/article/31022/Public-Spaces-Protect-Order-for-dog-controls">
          Public Spaces Protect Order for dog controls extended for three years
        </a></h2>
        <p>Dog controls will continue across Boston Borough.</p>
      </div>
    </body></html>
    """
    scraper = CouncilSourceScraper(SOURCE, config={
        "recency_days": 14, "max_listing_pages": 1, "request_timeout_seconds": 5
    })
    candidates, _next = scraper.parse_listing(html, SOURCE.url)
    assert len(candidates) == 1
    assert candidates[0].url.startswith("https://www.boston.gov.uk/article/31022/")


def test_boston_article_requires_and_extracts_full_text():
    candidate_html = """
    <html><body><main>
      <h1>Public Spaces Protect Order for dog controls extended for three years</h1>
      <p>Posted Thursday 1 October 2026</p>
      <div class="c-editable">
        <p>Boston Borough Council has extended its Public Spaces Protection Order for a further three years.</p>
        <p>The order includes controls intended to promote responsible dog ownership throughout the borough.</p>
        <p>Residents can read the full conditions and maps on the council website.</p>
      </div>
    </main></body></html>
    """
    scraper = CouncilSourceScraper(SOURCE, config={
        "recency_days": 14, "max_listing_pages": 1, "request_timeout_seconds": 5
    })
    candidates, _next = scraper.parse_listing(
        '<h2><a href="/article/31022/test">A sufficiently long Boston Council headline</a></h2>',
        SOURCE.url,
    )
    story = scraper._collect_detail_html(
        candidates[0], candidate_html, candidates[0].url, strict=True
    )
    assert "extended its Public Spaces Protection Order" in story.body
    assert len(story.body) >= 160
    assert story.published.startswith("2026-10-01")
    assert story.extras["source_key"] == "boston_borough_council"


def test_boston_challenge_is_detected():
    assert CouncilSourceScraper._is_challenge(
        "Just a moment... Performing security verification. Verify you are human"
    )
