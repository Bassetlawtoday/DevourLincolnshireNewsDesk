"""Official supplementary police publishers for Lincolnshire coverage."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from newsdesk.geography import story_matches_lincolnshire
from newsdesk.sources.police_scraper import (
    PoliceScraper,
    _ListingCandidate,
    _parse_police_publication_datetime,
)
from newsdesk.story import Story


class RegionalPolicePublisherScraper(PoliceScraper):
    """Reuse the proven rendered-page collector for an official publisher."""

    def __init__(
        self,
        *,
        source_name: str,
        base_url: str,
        listing_url: str,
        article_path_prefixes: tuple[str, ...],
        limit: int = 40,
    ) -> None:
        self.BASE_URL = base_url.rstrip("/")
        self.NEWS_URL = listing_url
        self.NEWS_SEARCH_URL = listing_url
        self.RSS_URL = ""
        self._allowed_hosts = {
            urlparse(self.BASE_URL).netloc.casefold(),
            urlparse(self.BASE_URL).netloc.casefold().removeprefix("www."),
            "www." + urlparse(self.BASE_URL).netloc.casefold().removeprefix("www."),
        }
        self._article_path_prefixes = tuple(value.casefold() for value in article_path_prefixes)
        super().__init__(limit=limit, headless=True)
        self.source_name = source_name
        self.source_url = listing_url

    def _is_article_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc.casefold() not in self._allowed_hosts:
            return False
        path = parsed.path.casefold()
        return any(
            marker in path and path.rstrip("/") != marker.rstrip("/")
            for marker in self._article_path_prefixes
        )

    def fetch_latest_news(self, limit: int | None = None) -> list[Story]:
        original_limit = self.limit
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be greater than zero.")
            self.limit = int(limit)
        try:
            stories = self.get_stories(refresh=True, deduplicate=True)
            return stories[: self.limit]
        finally:
            self.limit = original_limit
            if not self.keep_browser_open:
                self.close()


class LincolnshireAlertScraper(RegionalPolicePublisherScraper):
    """Collect Alert cards whose timestamps are absent from article pages."""

    ALERT_DATE_PATTERN = re.compile(
        r"\b(\d{1,2}/\d{1,2}/20\d{2}\s+\d{1,2}:\d{2}:\d{2})\b"
    )
    SENDER_PATTERN = re.compile(
        r"Message\s+Sent\s+By\s+(.+?)\s*\(([^)]+)\)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    ALERT_IMAGE_BLOCKLIST = (
        "/assets/bannerimage/",
        "/emailtemplates/",
        "/profilepictures/",
        "/surveyimagery/",
        "/msgicons/",
        "logo",
        "icon",
        "button",
    )

    def parse_article(self, response):
        """Preserve Alert-specific sender details and clean its article copy."""

        source_soup = BeautifulSoup(response.body, "html.parser")
        source_text = source_soup.get_text("\n", strip=True)
        sender_match = self.SENDER_PATTERN.search(source_text)
        alert_body = self._extract_alert_body(source_soup, response.url)
        alert_image = self._extract_alert_image(source_soup, response.url)

        story = super().parse_article(response)
        if story is None:
            return None

        story.body = self._clean_alert_body(alert_body or story.body, story.title)
        story.summary = self._clean_alert_summary("", story.body, story.title)

        if sender_match:
            sender_name = " ".join(sender_match.group(1).split()).strip(" -–—")
            sender_role = " ".join(sender_match.group(2).split()).strip()
            story.author = f"{sender_name} ({sender_role})"
            story.extras.update(
                {
                    "sender_name": sender_name,
                    "sender_role": sender_role,
                    "sender_attribution": f"Posted by {sender_name} ({sender_role})",
                }
            )

        if alert_image:
            story.image_url = alert_image
            story.image_alt_text = story.title
        if story.image_url:
            story.image_caption = story.title
            story.image_credit = "Lincolnshire Alert — Lincolnshire Police"

        return story

    def _extract_alert_body(self, soup: BeautifulSoup, article_url: str) -> str:
        """Return readable Alert copy with destination URLs made explicit."""

        container = soup.select_one("#emailPreviewContent, #content")
        if not isinstance(container, Tag):
            return ""

        # Work on a detached copy so sender extraction and image inspection
        # still see the untouched source document.
        fragment_soup = BeautifulSoup(str(container), "html.parser")
        fragment = fragment_soup.select_one("#emailPreviewContent, #content")
        if not isinstance(fragment, Tag):
            return ""

        for unwanted in fragment.select(
            "script, style, form, iframe, svg, "
            "a[href*='/Alerts/WebReply/'], "
            "a[href*='facebook.com/share'], "
            "a[href*='twitter.com/intent/']"
        ):
            unwanted.decompose()

        seen_links: set[str] = set()
        for anchor in list(fragment.find_all("a", href=True)):
            href = urljoin(article_url, str(anchor.get("href") or "").strip())
            label = " ".join(anchor.get_text(" ", strip=True).split())
            if not href:
                anchor.decompose()
                continue
            if not label:
                # Image-only buttons are followed by an accessible text link
                # on Alert pages; retain that text link once instead.
                anchor.decompose()
                continue
            if href.casefold() in seen_links:
                anchor.decompose()
                continue
            seen_links.add(href.casefold())
            anchor.replace_with(f"{label} — {href}")

        for image in fragment.find_all("img"):
            image.decompose()
        for line_break in fragment.find_all("br"):
            line_break.replace_with("\n")

        lines: list[str] = []
        seen_lines: set[str] = set()
        for raw_line in fragment.get_text("\n", strip=True).splitlines():
            line = " ".join(raw_line.replace("\xa0", " ").split()).strip()
            lowered = line.casefold()
            if not line or lowered in {
                "reply to this message",
                "share",
                "share facebook",
                "share x",
            }:
                continue
            if lowered in seen_lines:
                continue
            seen_lines.add(lowered)
            lines.append(line)
        return "\n\n".join(lines)

    def _extract_alert_image(self, soup: BeautifulSoup, article_url: str) -> str:
        """Choose the editorial photograph, never Alert page furniture."""

        container = soup.select_one("#emailPreviewContent, #content")
        if not isinstance(container, Tag):
            return ""
        candidates: list[tuple[int, str]] = []
        for image in container.find_all("img"):
            if image.find_parent("a") is not None:
                # Linked survey graphics and buttons are calls to action, not
                # story photographs.
                continue
            image_url = self._image_url_from_element(image, article_url)
            lowered = image_url.casefold()
            if not image_url or any(term in lowered for term in self.ALERT_IMAGE_BLOCKLIST):
                continue
            width = self._integer_attribute(image, "width")
            height = self._integer_attribute(image, "height")
            score = width * height
            if re.search(r"/\d+/\d+/[0-9a-f-]+\.(?:jpe?g|png|webp)(?:\?|$)", lowered):
                score += 1_000_000
            candidates.append((score, image_url))
        return max(candidates, default=(0, ""), key=lambda item: item[0])[1]

    @staticmethod
    def _integer_attribute(element: Tag, name: str) -> int:
        match = re.search(r"\d+", str(element.get(name) or ""))
        return int(match.group(0)) if match else 0

    @staticmethod
    def _clean_alert_body(body: str, title: str) -> str:
        paragraphs = [
            " ".join(value.split())
            for value in re.split(r"\n\s*\n|\r\n\s*\r\n", str(body or ""))
            if " ".join(value.split())
        ]
        title_key = " ".join(str(title or "").split()).casefold().rstrip(" .")
        cleaned: list[str] = []
        for paragraph in paragraphs:
            key = paragraph.casefold().rstrip(" .")
            if key == title_key:
                continue
            if cleaned and key == cleaned[-1].casefold().rstrip(" ."):
                continue
            cleaned.append(paragraph)

        # The shared parser can prepend an abbreviated lead before the full
        # Alert article. Drop it when the next paragraph begins with the same
        # words, retaining the complete version only.
        if len(cleaned) > 1 and cleaned[0].endswith(("…", "...")):
            lead = cleaned[0].rstrip(".… ").casefold()
            if any(item.casefold().startswith(lead) for item in cleaned[1:]):
                cleaned.pop(0)
        return "\n\n".join(cleaned)

    @staticmethod
    def _clean_alert_summary(summary: str, body: str, title: str) -> str:
        value = " ".join(str(summary or "").split()).strip()
        if value.casefold().rstrip(" .") == " ".join(str(title or "").split()).casefold().rstrip(" ."):
            value = ""
        if value:
            return value
        first_paragraph = str(body or "").split("\n\n", 1)[0].strip()
        return first_paragraph

    def _extract_listing_candidates(
        self,
        html: str,
        page_url: str,
    ) -> list[_ListingCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[_ListingCandidate] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href*='/Alerts/A/']"):
            if not isinstance(anchor, Tag):
                continue
            absolute_url = self._normalise_url(str(anchor.get("href") or ""))
            if not self._is_article_url(absolute_url):
                continue
            key = absolute_url.casefold().rstrip("/")
            if key in seen:
                continue

            context: Tag | None = anchor
            card_text = ""
            raw_published = ""
            for _ in range(7):
                if context is None:
                    break
                candidate_text = context.get_text("\n", strip=True)
                date_match = self.ALERT_DATE_PATTERN.search(candidate_text)
                if date_match:
                    card_text = candidate_text
                    raw_published = date_match.group(1)
                    break
                context = context.parent if isinstance(context.parent, Tag) else None

            if not raw_published:
                continue
            lines = [line.strip() for line in card_text.splitlines() if line.strip()]
            title = next(
                (
                    line
                    for line in lines
                    if line.casefold() not in {"view alert", "lincolnshire police"}
                    and not self.ALERT_DATE_PATTERN.fullmatch(line)
                ),
                "Lincolnshire Alert",
            )
            seen.add(key)
            candidates.append(
                _ListingCandidate(
                    url=absolute_url,
                    title=title,
                    published=_parse_police_publication_datetime(raw_published),
                    raw_published=raw_published,
                )
            )
        return candidates


def _regional_scrapers() -> tuple[tuple[RegionalPolicePublisherScraper, bool], ...]:
    """Return official collectors and whether Lincolnshire filtering is required."""

    return (
        (
            LincolnshireAlertScraper(
                source_name="Lincolnshire Alert",
                base_url="https://www.lincolnshirealert.co.uk",
                listing_url="https://www.lincolnshirealert.co.uk/Content/Pages/Latest-Alerts",
                article_path_prefixes=("/alerts/a/",),
                limit=40,
            ),
            False,
        ),
        (
            RegionalPolicePublisherScraper(
                source_name="Lincolnshire Police and Crime Commissioner",
                base_url="https://lincolnshire-pcc.gov.uk",
                listing_url="https://lincolnshire-pcc.gov.uk/news/",
                article_path_prefixes=("/2026/", "/2025/"),
                limit=30,
            ),
            False,
        ),
        (
            RegionalPolicePublisherScraper(
                source_name="Humberside Police",
                base_url="https://www.humberside.police.uk",
                listing_url="https://www.humberside.police.uk/news/news-search/?ct=News&q=Scunthorpe",
                article_path_prefixes=("/news/humberside/news/",),
                limit=40,
            ),
            True,
        ),
        (
            RegionalPolicePublisherScraper(
                source_name="Humberside Police",
                base_url="https://www.humberside.police.uk",
                listing_url="https://www.humberside.police.uk/news/news-search/?ct=News&q=Grimsby",
                article_path_prefixes=("/news/humberside/news/",),
                limit=40,
            ),
            True,
        ),
    )


def collect_regional_police_sources() -> tuple[list[Story], list[str]]:
    """Collect official supplementary sources with explainable geo filtering."""

    stories: list[Story] = []
    errors: list[str] = []
    for scraper, requires_filter in _regional_scrapers():
        try:
            collected = scraper.fetch_latest_news()
            for story in collected:
                if requires_filter:
                    match = story_matches_lincolnshire(story)
                    if not match.matched:
                        continue
                    story.extras.setdefault("geographic_filter", "lincolnshire")
                    story.extras.setdefault("geographic_matches", list(match.places))
                story.category = story.category or "Police"
                story.extras.setdefault("module_profile", "police")
                story.extras.setdefault("official_regional_source", True)
                stories.append(story)
        except Exception as error:
            errors.append(f"{scraper.source_name}: {error}")
        finally:
            scraper.close()
    return stories, errors


__all__ = [
    "RegionalPolicePublisherScraper",
    "LincolnshireAlertScraper",
    "collect_regional_police_sources",
]
