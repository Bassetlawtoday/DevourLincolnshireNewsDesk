"""Downloads Nottinghamshire Police news articles."""


from __future__ import annotations


import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from services.models import PoliceArticle


class PoliceScraper:
    """Collect articles from the Nottinghamshire Police news website."""

    BASE_URL = "https://www.nottinghamshire.police.uk"
    NEWS_URL = f"{BASE_URL}/news/news-search/"

    def __init__(self) -> None:
        options = Options()
        options.add_argument("--start-maximized")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)
        self.articles: list[PoliceArticle] = []

    def close(self) -> None:
        """Close the browser safely."""
        try:
            self.driver.quit()
        except Exception:
            pass

    def open_news_page(self) -> bool:
        """Open the police news page with retries and increasing waits."""
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                print(
                    f"Opening Nottinghamshire Police news "
                    f"(attempt {attempt}/{max_attempts})..."
                )

                self.driver.get(self.NEWS_URL)

                self.wait.until(
                    lambda driver: driver.execute_script(
                        "return document.readyState"
                    ) == "complete"
                )

                time.sleep(1.5)

                page_text = self.driver.page_source.lower()

                if "too many requests" in page_text or "error 429" in page_text:
                    wait_time = 30 * attempt
                    print(
                        f"Rate limit detected. Waiting {wait_time} seconds..."
                    )
                    time.sleep(wait_time)
                    continue

                if not self.driver.page_source.strip():
                    raise RuntimeError("The police news page returned no HTML.")

                print("Police news page loaded.")
                return True

            except (TimeoutException, WebDriverException, RuntimeError) as error:
                if attempt == max_attempts:
                    print(
                        "Police news page could not be loaded after "
                        f"{max_attempts} attempts: {error}"
                    )
                    return False

                wait_time = 3 * attempt
                print(
                    f"Page failed to load. Waiting {wait_time} seconds "
                    "before retrying..."
                )
                time.sleep(wait_time)

        return False
    
    def fetch_latest_news(self, limit: int = 20):
        """
        Download and analyse the latest police news stories.
        Returns a list of NewsStory objects sorted by publication order.
        """

        stories = []

        links = self.fetch_article_links(limit=limit)

        for link in links:
            try:
                story = self.scrape_and_analyse(link)

                if story:
                    stories.append(story)

            except Exception as ex:
                print(f"Failed to analyse: {link}")
                print(f"Reason: {ex}")

        stories.sort(
            key=lambda story: story.score,
            reverse=True,
        )

        return stories


    
    
    
    def fetch_article_links(self, limit: int = 10) -> list[str]:
        """Extract unique news article links from the loaded page."""
        if limit < 1:
            return []

        if not self.open_news_page():
            return []

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        links: list[str] = []

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()

            if not self._is_article_path(href):
                continue

            url = urljoin(self.BASE_URL, href)

            if url not in links:
                links.append(url)

            if len(links) >= limit:
                break

        return links
    

    def scrape_article(self, url: str) -> PoliceArticle | None:
        """Download and parse one Nottinghamshire Police article."""
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                print()
                print(
                    f"Opening police article "
                    f"(attempt {attempt}/{max_attempts})..."
                )
                print(url)

                # A variable pause helps avoid sending requests at a rigid rate.
                pause = 1.5 + ((attempt - 1) * 0.75)
                time.sleep(pause)

                self.driver.get(url)

                self.wait.until(
                    lambda driver: driver.execute_script(
                        "return document.readyState"
                    ) == "complete"
                )

                self.wait.until(
                    lambda driver: bool(
                        BeautifulSoup(
                            driver.page_source,
                            "html.parser",
                        ).find("h1")
                    )
                )

                time.sleep(0.75)

                page_text = self.driver.page_source.lower()

                if self._is_rate_limited(page_text):
                    wait_time = 30 * attempt
                    print(
                        f"Rate limit detected. Waiting {wait_time} seconds "
                        "before retrying..."
                    )
                    time.sleep(wait_time)
                    continue

                article = self._parse_article_html(
                    html=self.driver.page_source,
                    url=url,
                )

                if not article.headline:
                    raise RuntimeError(
                        "The article page did not contain a headline."
                    )

                print(f"Article downloaded: {article.headline}")
                return article

            except (TimeoutException, WebDriverException, RuntimeError) as error:
                if attempt == max_attempts:
                    print(
                        f"Skipping article after {max_attempts} attempts: "
                        f"{error}"
                    )
                    return None

                wait_time = 3 * attempt
                print(
                    f"Article failed to load. Waiting {wait_time} seconds "
                    "before retrying..."
                )
                time.sleep(wait_time)

        return None
    
    def scrape_and_analyse(self, url: str):
        """Download a police article and convert it into a scored NewsStory."""

        article = self.scrape_article(url)

        if article is None:
            return None

        from editorial.police_analysis import analyse_police_article

        return analyse_police_article(article)

    def _parse_article_html(
        self,
        html: str,
        url: str,
    ) -> PoliceArticle:
        """Convert article-page HTML into a PoliceArticle object."""
        soup = BeautifulSoup(html, "html.parser")

        article = PoliceArticle()
        article.source_url = url

        article.headline = self._extract_headline(soup)
        article.summary = self._extract_summary(soup)
        article.published_date = self._extract_published_date(soup)
        article.body = self._extract_body(soup)
        article.location = self._extract_location(soup, article.body)
        article.reference = self._extract_reference(
            f"{article.summary} {article.body}"
        )
        article.quotes = self._extract_quotes(soup)
        article.images = self._extract_images(soup, url)

        return article

    @staticmethod
    def _clean_text(value: object) -> str:
        """Normalise whitespace in text extracted from HTML."""
        return " ".join(str(value or "").split())

    def _extract_headline(self, soup: BeautifulSoup) -> str:
        """Extract the article headline."""
        heading = soup.find("h1")

        if heading:
            return self._clean_text(heading.get_text(" ", strip=True))

        meta_title = soup.find("meta", property="og:title")

        if meta_title:
            return self._clean_text(meta_title.get("content", ""))

        if soup.title:
            return self._clean_text(soup.title.get_text(" ", strip=True))

        return ""

    def _extract_summary(self, soup: BeautifulSoup) -> str:
        """Extract the article summary or social description."""
        selectors = (
            "meta[name='description']",
            "meta[property='og:description']",
            "meta[name='twitter:description']",
        )

        for selector in selectors:
            element = soup.select_one(selector)

            if element:
                content = self._clean_text(element.get("content", ""))

                if content:
                    return content

        return ""

    def _extract_published_date(self, soup: BeautifulSoup) -> str:
        """Extract the publication date from a Nottinghamshire Police article."""

        # Nottinghamshire Police layout
        meta = soup.select_one(".c-news-panel_status")

        if meta:
            text = self._clean_text(meta.get_text(" ", strip=True))

            text = text.replace("Published :", "")
            text = text.replace("Published:", "")
            text = text.strip()

            if text:
                return text

        # Generic fallbacks
        selectors = (
            "time[datetime]",
            "meta[property='article:published_time']",
            "meta[name='article:published_time']",
        )

        for selector in selectors:
            element = soup.select_one(selector)

            if not element:
                continue

            value = (
                element.get("datetime")
                or element.get("content")
                or element.get_text(" ", strip=True)
            )

            value = self._clean_text(value)

            if value:
                return value

        return ""
    
    def _find_article_container(self, soup: BeautifulSoup):
        """Find the main content container for a police news article."""

        selectors = (
            ".c-news-panel_content",
            ".c-news-panel",
            "main article",
            "article",
            "main",
        )

        for selector in selectors:
            container = soup.select_one(selector)

            if container:
                return container

        return soup

    def _extract_body(self, soup: BeautifulSoup) -> str:
        """Extract readable article paragraphs."""
        container = self._find_article_container(soup)
        paragraphs: list[str] = []

        excluded_phrases = (
            "without javascript enabled forms will not work",
            "share this page",
            "cookie",
            "privacy",
            "sign up",
            "skip to main content",
            "follow us",
            "copyright",
        )

        for paragraph in container.find_all("p"):
            text = self._clean_text(
                paragraph.get_text(" ", strip=True)
            )

            if not text:
                continue

            lowered = text.lower()

            if any(
                phrase in lowered
                for phrase in excluded_phrases
            ):
                continue

            if text not in paragraphs:
                paragraphs.append(text)

        body = "\n\n".join(paragraphs)

        body = body.replace(
            "Without JavaScript enabled forms will not work.\n\n",
            "",
        )

        return body.strip()

    def _extract_location(
        self,
        soup: BeautifulSoup,
        body: str,
    ) -> str:
        """Extract an explicitly labelled article location when available."""
        location_selectors = (
            "[class*='location']",
            "[itemprop='contentLocation']",
            "[data-location]",
        )

        for selector in location_selectors:
            element = soup.select_one(selector)

            if not element:
                continue

            value = (
                element.get("data-location")
                or element.get_text(" ", strip=True)
            )

            value = self._clean_text(value)

            if value and len(value) <= 100:
                return value

        # Leave detailed place recognition to the editorial priority engine.
        return ""

    @staticmethod
    def _extract_reference(text: str) -> str:
        """Find a police incident or appeal reference when one is published."""
        patterns = (
            r"\bincident\s+(?:number|reference|ref\.?)?\s*:?\s*([0-9]{3,8})\b",
            r"\bcrime\s+(?:number|reference|ref\.?)?\s*:?\s*([A-Z0-9/-]{5,})\b",
            r"\breference\s*:?\s*([A-Z0-9/-]{5,})\b",
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if match:
                return match.group(1).strip()

        return ""

    def _extract_quotes(self, soup: BeautifulSoup) -> list[str]:
        """Extract blockquotes and clearly quoted paragraphs."""
        container = self._find_article_container(soup)
        quotes: list[str] = []

        for element in container.find_all("blockquote"):
            text = self._clean_text(
                element.get_text(" ", strip=True)
            )

            if text and text not in quotes:
                quotes.append(text)

        quote_characters = ('"', "“", "‘")

        for paragraph in container.find_all("p"):
            text = self._clean_text(
                paragraph.get_text(" ", strip=True)
            )

            if not text:
                continue

            if text.startswith(quote_characters):
                if text not in quotes:
                    quotes.append(text)

        return quotes

    def _extract_images(
        self,
        soup: BeautifulSoup,
        page_url: str,
    ) -> list[str]:
        """Extract unique article image URLs."""
        container = self._find_article_container(soup)
        images: list[str] = []

        social_image = soup.select_one("meta[property='og:image']")

        if social_image:
            source = self._clean_text(
                social_image.get("content", "")
            )

            if source:
                images.append(urljoin(page_url, source))

        for image in container.find_all("img"):
            source = (
                image.get("src")
                or image.get("data-src")
                or image.get("data-lazy-src")
                or ""
            )

            source = self._clean_text(source)

            if not source:
                continue

            image_url = urljoin(page_url, source)

            if image_url not in images:
                images.append(image_url)

        return images

    @staticmethod
    def _is_rate_limited(page_text: str) -> bool:
        """Identify common rate-limit and temporary blocking pages."""
        indicators = (
            "too many requests",
            "error 429",
            "429 too many requests",
            "rate limit exceeded",
            "temporarily blocked",
        )

        return any(
            indicator in page_text
            for indicator in indicators
        )


    @staticmethod
    def _is_article_path(href: str) -> bool:
        """Return True when a link appears to be a police news article."""
        if not href:
            return False

        path = href.split("?", 1)[0].rstrip("/").lower()

        return (
            "/news/" in path
            and "/news-search" not in path
            and path != "/news"
        )