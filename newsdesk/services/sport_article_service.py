"""
Selected-story article enrichment for Sport Intelligence.

This service keeps network extraction and StoryEngine processing outside the
Sport user interface. It enriches one existing Story at a time and never
participates in RSS collection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag
import requests

from newsdesk.publish_result import PublishResult
from newsdesk.services.image_service import ImageService
from newsdesk.sources.article_scraper import ArticleScraper
from newsdesk.sports.media_policy import choose_article_still, is_still_image_url
from newsdesk.story import Story
from newsdesk.story_engine import StoryEngine


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SportArticleResult:
    """Outcome of enriching one selected Sport story."""

    story: Story
    publish_result: PublishResult | None = None
    successful: bool = False
    body_updated: bool = False
    author_updated: bool = False
    published_updated: bool = False
    tags_updated: bool = False
    word_count: int = 0
    canonical_url: str = ""
    categories: list[str] = field(default_factory=list)
    extracted_tags: list[str] = field(default_factory=list)
    error: str = ""
    processing_error: str = ""


class SportArticleService:
    """
    Fetch and apply full article content for one selected Sport story.

    RSS discovery remains separate and fast. This service is intended to run
    from a background worker after an editor selects a story.
    """

    _API_IMAGE_REJECT_TERMS = (
        "avatar",
        "badge",
        "crest",
        "favicon",
        "icon",
        "logo",
        "pixel",
        "placeholder",
        "social-share",
        "sprite",
        "tracking",
    )
    _API_CONTENT_TAGS = ("h2", "h3", "h4", "p", "blockquote", "li")
    _API_BOILERPLATE = (
        re.compile(r"^advertisement\b", re.IGNORECASE),
        re.compile(r"^(?:buy|book) tickets?\b", re.IGNORECASE),
        re.compile(r"^related (?:articles|stories|news)\b", re.IGNORECASE),
        re.compile(r"^(?:sign up|subscribe)\b", re.IGNORECASE),
        re.compile(r"^share (?:this|on|via)\b", re.IGNORECASE),
        re.compile(r"^created by\s*:", re.IGNORECASE),
        re.compile(r"^posted in\s*:", re.IGNORECASE),
    )

    def __init__(
        self,
        *,
        timeout: float = 25.0,
        article_scraper_factory: Any = None,
        story_engine: StoryEngine | None = None,
    ) -> None:
        self.timeout = float(timeout)
        self.article_scraper_factory = (
            article_scraper_factory
            or self._default_article_scraper_factory
        )
        self.story_engine = story_engine or StoryEngine(
            strict_validation=False,
            strict_formatting=False,
        )
        self._image_service_instance: ImageService | None = None

    def needs_enrichment(self, story: Story) -> bool:
        """Return True when the story still contains only feed-level copy."""

        self._validate_story(story)

        url = str(story.url or "").strip()
        if not url:
            return False

        status = str(
            story.extras.get("article_content_status", "") or ""
        ).strip()

        if status == "loading":
            return False

        if not is_still_image_url(story.image_url) or story.image_is_fallback:
            return True

        if status == "complete":
            return False

        body = self._normalise_text(story.body)
        summary = self._normalise_text(story.summary)

        if not body:
            return True

        if summary and body.casefold() == summary.casefold():
            return True

        return len(body) < 350

    def enrich(self, story: Story) -> SportArticleResult:
        """
        Enrich ``story`` in place and return a structured result.

        Extraction and StoryEngine failures are captured rather than raised so
        the existing RSS story remains usable.
        """

        self._validate_story(story)

        result = SportArticleResult(story=story)
        url = str(story.url or "").strip()

        if not url:
            result.error = "The story does not contain an article URL."
            self._store_failure(story, result.error)
            return result

        story.extras.update(
            {
                "article_content_status": "loading",
                "article_content_error": "",
            }
        )

        html_article: dict[str, Any] = {}
        html_error = ""
        scraper = self.article_scraper_factory()
        try:
            html_article = scraper.extract_article(
                url,
                body_selector="",
                image_selector=None,
            )
        except Exception as error:
            html_error = str(error)
        finally:
            close_method = getattr(scraper, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    pass

        html_body = str(html_article.get("text", "") or "").strip()
        LOGGER.debug(
            "Sport article HTML extraction source=%s url=%s succeeded=%s "
            "body_chars=%d failure=%s",
            story.source,
            url,
            bool(html_body),
            len(html_body),
            html_error or ("" if html_body else "no viable body"),
        )

        api_article: dict[str, Any] = {}
        api_error = ""
        if not html_body and self._has_configured_article_api(story):
            api_article, api_error = self._extract_configured_api_article(story)

        article = html_article if html_body else api_article
        body = self._normalise_article_layout(article.get("text", ""))
        author = self._normalise_text(article.get("author", ""))
        published = str(article.get("published", "") or "").strip()
        canonical = str(article.get("canonical", "") or "").strip()
        categories = self._clean_list(article.get("categories", []))
        extracted_tags = self._clean_list(article.get("tags", []))
        self._apply_article_summary(story, article)
        self._apply_article_image(
            story,
            api_article=api_article,
            html_article=html_article,
        )

        current_body = str(story.body or "").strip()

        if body and (
            not current_body
            or len(body) > len(current_body)
        ):
            story.body = body
            result.body_updated = True

        if author and author != str(story.author or "").strip():
            story.author = author
            result.author_updated = True

        if (
            published
            and not str(story.published or "").strip()
        ):
            story.published = published
            result.published_updated = True

        merged_tags = self._merge_unique(
            list(story.tags or []),
            extracted_tags,
        )
        if merged_tags != list(story.tags or []):
            story.tags = merged_tags
            result.tags_updated = True

        word_count = (
            len(re.findall(r"\b[\w’'-]+\b", body))
            if body
            else 0
        )

        result.word_count = word_count
        result.canonical_url = canonical
        result.categories = categories
        result.extracted_tags = extracted_tags
        result.successful = bool(body)

        story.extras.update(
            {
                "article_content_status": (
                    "complete"
                    if body
                    else "failed"
                ),
                "article_content_error": (
                    ""
                    if body
                    else "No full article body was found."
                ),
                "article_content_word_count": word_count,
                "article_content_author": author,
                "article_content_published": published,
                "article_content_canonical": canonical,
                "article_content_categories": categories,
                "article_content_tags": extracted_tags,
                "article_content_paragraph_count": self._paragraph_count(body),
                "article_content_extraction_source": (
                    "html" if html_body else "api" if body else "none"
                ),
            }
        )

        if not body:
            result.error = (
                api_error
                or html_error
                or "No full article body was found."
            )

        try:
            result.publish_result = self.story_engine.process(story)
        except Exception as error:
            result.processing_error = str(error)
            story.extras[
                "article_content_processing_error"
            ] = result.processing_error

        return result

    @staticmethod
    def _has_configured_article_api(story: Story) -> bool:
        return bool(str(story.extras.get("content_api_url", "") or "").strip())

    def _extract_configured_api_article(
        self,
        story: Story,
    ) -> tuple[dict[str, Any], str]:
        endpoint = self._article_api_endpoint(story)
        if not endpoint:
            return {}, "Configured article API endpoint was not safe or valid."

        LOGGER.debug(
            "Sport article API fallback source=%s url=%s endpoint=%s attempted=true",
            story.source,
            story.url,
            self._endpoint_for_log(endpoint),
        )
        try:
            response = requests.get(
                endpoint,
                headers=ArticleScraper.DEFAULT_HEADERS,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            message = f"Article API fallback failed: {error}"
            self._log_api_failure(story, endpoint, message)
            return {}, message

        record = self._api_article_record(payload)
        if not record:
            message = "Article API response structure was not recognised."
            self._log_api_failure(story, endpoint, message)
            return {}, message

        article = self._normalise_api_article(story, record)
        body = str(article.get("text", "") or "")
        LOGGER.debug(
            "Sport article API source=%s url=%s structure=recognised "
            "body_chars=%d words=%d paragraphs=%d api_image=%s "
            "caption=%s credit=%s",
            story.source,
            story.url,
            len(body),
            len(re.findall(r"\b[\wâ€™'-]+\b", body)),
            self._paragraph_count(body),
            bool(article.get("image")),
            bool(article.get("image_caption")),
            bool(article.get("image_credit")),
        )
        if not body:
            return article, "Article API contained no viable article body."
        return article, ""

    def _article_api_endpoint(self, story: Story) -> str:
        configured = str(story.extras.get("content_api_url", "") or "").strip()
        parsed = urlparse(configured)
        article = urlparse(str(story.url or "").strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or ".cms.web.gc." not in parsed.hostname.casefold()
            or article.scheme not in {"http", "https"}
            or not article.hostname
        ):
            return ""

        path = re.sub(r"/v2/search/?$", "/v1/byslug", parsed.path)
        if path == parsed.path:
            return ""
        query = urlencode({"postSlug": article.path})
        return urlunparse((parsed.scheme, parsed.netloc, path, "", query, ""))

    @staticmethod
    def _endpoint_for_log(endpoint: str) -> str:
        parsed = urlparse(endpoint)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    @staticmethod
    def _api_article_record(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        body = payload.get("body")
        if not isinstance(body, list) or not body or not isinstance(body[0], dict):
            return {}
        return body[0]

    def _normalise_api_article(
        self,
        story: Story,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        blocks = record.get("content")
        paragraphs: list[str] = []
        if isinstance(blocks, list):
            for block in blocks:
                paragraphs.extend(self._api_block_text(block))

        image_data = record.get("imageData") or {}
        image_url, image_width, image_height = self._api_image(
            image_data,
            story=story,
        )
        image_url = urljoin(story.url, image_url)
        if not self._valid_api_image(
            image_url,
            story=story,
            width=image_width,
            height=image_height,
        ):
            image_url = ""

        canonical_path = str(record.get("postSlug") or "").strip()
        canonical = (
            urljoin(story.url, canonical_path)
            if canonical_path
            else str(story.url or "").strip()
        )
        return {
            "text": "\n\n".join(paragraphs).strip(),
            "title": self._normalise_text(record.get("postTitle")),
            "summary": self._first_text(
                record,
                "standfirst",
                "description",
                "metaDescription",
            ),
            "author": self._first_text(record, "postAuthor", "author"),
            "published": str(record.get("publishedDateTime") or "").strip(),
            "canonical": canonical,
            "categories": self._clean_list(record.get("postCategoryName", "")),
            "tags": self._api_tags(record.get("tagsData")),
            "image": image_url,
            "image_width": image_width,
            "image_height": image_height,
            "image_caption": self._first_text(
                image_data,
                "caption",
                "description",
            ),
            "image_credit": self._first_text(
                image_data,
                "photographer",
                "credit",
                "copyright",
                "source",
            ),
        }

    def _api_block_text(self, block: Any) -> list[str]:
        if not isinstance(block, dict):
            return []
        row_data = block.get("rowData")
        if not isinstance(row_data, dict):
            return []
        widget_data = row_data.get("widgetData")
        if not isinstance(widget_data, dict):
            return []
        values = [
            widget_data.get("content"),
            widget_data.get("contentDouble"),
            widget_data.get("quote"),
        ]
        result: list[str] = []
        for value in values:
            if not isinstance(value, str) or "<" not in value:
                continue
            soup = BeautifulSoup(value, "html.parser")
            for node in soup.find_all(self._API_CONTENT_TAGS):
                if (
                    node.name == "li"
                    and isinstance(node.parent, Tag)
                    and node.parent.name == "li"
                ):
                    continue
                text = self._normalise_text(node.get_text(" ", strip=True))
                if text and not any(pattern.search(text) for pattern in self._API_BOILERPLATE):
                    result.append(text)
            if not result:
                for line in soup.get_text("\n", strip=True).splitlines():
                    text = self._normalise_text(line)
                    if text and not any(
                        pattern.search(text)
                        for pattern in self._API_BOILERPLATE
                    ):
                        result.append(text)
        return result

    @staticmethod
    def _api_image(
        image_data: Any,
        *,
        story: Story,
    ) -> tuple[str, int, int]:
        if not isinstance(image_data, dict):
            return "", 0, 0
        candidates: list[tuple[int, str, int, int]] = []
        for value in [image_data, *image_data.values()]:
            if not isinstance(value, dict):
                continue
            url = str(
                value.get("location")
                or value.get("Location")
                or value.get("url")
                or ""
            ).strip()
            try:
                width = int(value.get("width") or 0)
                height = int(value.get("height") or 0)
            except (TypeError, ValueError):
                width = height = 0
            if url:
                candidates.append((width * height, url, width, height))
        if not candidates:
            return "", 0, 0
        _, url, width, height = max(candidates, key=lambda item: item[0])
        key = str(image_data.get("key") or "").strip().lstrip("/")
        api_host = urlparse(
            str(story.extras.get("content_api_url", ""))
        ).hostname or ""
        media_suffix = api_host.split(".cms.web.gc.", 1)[-1].casefold()
        if key and media_suffix and media_suffix != api_host.casefold():
            url = f"https://images.gc.{media_suffix}/fit-in/1600x900/{key}"
            width = max(width, 1600)
            height = max(height, 900)
        return url, width, height

    def _valid_api_image(
        self,
        url: str,
        *,
        story: Story,
        width: int,
        height: int,
    ) -> bool:
        parsed = urlparse(urljoin(story.url, url))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        lowered = url.casefold()
        if any(term in lowered for term in self._API_IMAGE_REJECT_TERMS):
            return False
        if (width and width < 300) or (height and height < 180):
            return False
        api_host = urlparse(
            str(story.extras.get("content_api_url", ""))
        ).hostname or ""
        media_suffix = api_host.split(".cms.web.gc.", 1)[-1].casefold()
        host = parsed.hostname.casefold()
        return bool(
            media_suffix
            and (host == media_suffix or host.endswith(f".{media_suffix}"))
        )

    def _apply_article_summary(self, story: Story, article: dict[str, Any]) -> None:
        summary = self._normalise_text(article.get("summary", ""))
        existing = self._normalise_text(story.summary)
        if self._meaningful_summary(summary):
            story.summary = summary
        elif self._meaningful_summary(existing):
            story.summary = existing
        else:
            generated = self._generated_summary(article.get("text", ""))
            if generated:
                story.summary = generated

    @classmethod
    def _normalise_article_layout(cls, value: Any) -> str:
        """Preserve useful paragraphs and make single-block articles readable."""

        raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = [cls._normalise_text(part) for part in re.split(r"\n\s*\n", raw)]
        paragraphs = [part for part in paragraphs if part]
        if len(paragraphs) > 1:
            return "\n\n".join(paragraphs)
        text = paragraphs[0] if paragraphs else cls._normalise_text(raw)
        if len(text) < 500:
            return text

        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9‘“])", text)
        if len(sentences) < 3:
            return text
        grouped = [" ".join(sentences[index:index + 2]).strip() for index in range(0, len(sentences), 2)]
        return "\n\n".join(part for part in grouped if part)

    def _apply_article_image(
        self,
        story: Story,
        *,
        api_article: dict[str, Any],
        html_article: dict[str, Any],
    ) -> None:
        listing_image = str(story.image_url or "").strip()
        listing_local_path = str(story.image_local_path or "").strip()
        api_image = str(api_article.get("image", "") or "").strip()
        html_image = choose_article_still(
            html_article,
            str(story.url or "").strip(),
        )

        caption = self._normalise_text(api_article.get("image_caption", ""))
        credit = self._normalise_text(api_article.get("image_credit", ""))
        final_source = "none"
        attempted_urls: set[str] = set()
        for source, candidate in (
            ("API", api_image),
            ("listing", listing_image),
            ("HTML/OpenGraph", html_image),
        ):
            if not candidate or candidate in attempted_urls:
                continue
            attempted_urls.add(candidate)

            if (
                source == "listing"
                and listing_local_path
                and Path(listing_local_path).is_file()
                and not story.image_is_fallback
            ):
                final_source = source
                break

            asset = self._image_service().get(
                candidate,
                fallback_title=story.title or "Sport Intelligence",
            )
            if not asset.available or asset.is_fallback:
                continue
            story.attach_image(
                asset,
                caption=caption or story.image_caption,
                credit=credit or story.image_credit,
                alt_text=story.image_alt_text,
            )
            final_source = source
            break

        if final_source == "none" and listing_image:
            story.image_url = listing_image
            story.image_local_path = listing_local_path
        if caption and final_source == "API":
            story.image_caption = caption
        if credit and final_source == "API":
            story.image_credit = credit

        final_path = str(story.image_local_path or "").strip()
        cache_key = Path(final_path).stem if final_path else ""
        story.extras.update(
            {
                "article_listing_image_url": listing_image,
                "article_api_image_url": api_image,
                "article_html_image_url": html_image,
                "article_image_source": final_source,
                "image_source_url": story.image_url,
                "image_cache_key": cache_key,
                "image_download_status": (
                    "cached" if story.image_cached else "downloaded"
                ) if final_path else "failed",
            }
        )
        LOGGER.debug(
            "Sport article image source=%s url=%s listing=%s api=%s "
            "final_source=%s final_url=%s local_path=%s cache_key=%s "
            "dimensions=%dx%d caption=%s credit=%s",
            story.source,
            story.url,
            bool(listing_image),
            bool(api_image),
            final_source,
            story.image_url,
            final_path,
            cache_key,
            story.image_width,
            story.image_height,
            bool(story.image_caption),
            bool(story.image_credit),
        )

    def _image_service(self) -> ImageService:
        if self._image_service_instance is None:
            self._image_service_instance = ImageService(timeout=self.timeout)
        return self._image_service_instance

    @classmethod
    def _meaningful_summary(cls, value: Any) -> bool:
        text = cls._normalise_text(value)
        if len(text.split()) < 8:
            return False
        return not any(pattern.search(text) for pattern in cls._API_BOILERPLATE)

    @classmethod
    def _generated_summary(cls, body: Any) -> str:
        parts = [
            cls._normalise_text(part)
            for part in re.split(r"\n\s*\n", str(body or ""))
        ]
        meaningful = [
            part
            for part in parts
            if len(part.split()) >= 5
            and not re.fullmatch(
                r"(?:first|second) half|match report|report",
                part,
                flags=re.IGNORECASE,
            )
            and not any(pattern.search(part) for pattern in cls._API_BOILERPLATE)
        ]
        if not meaningful:
            return ""

        selected: list[str] = []
        for part in meaningful[:2]:
            selected.extend(part.split())
            if len(selected) >= 25:
                break
        return " ".join(selected[:60]).strip()

    @classmethod
    def _api_tags(cls, value: Any) -> list[str]:
        if not isinstance(value, dict):
            return []
        tags: list[str] = []
        for items in value.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    name = cls._normalise_text(item.get("name"))
                    if name and name not in tags:
                        tags.append(name)
        return tags

    @classmethod
    def _first_text(cls, value: Any, *keys: str) -> str:
        if not isinstance(value, dict):
            return ""
        for key in keys:
            text = cls._normalise_text(value.get(key))
            if text:
                return text
        return ""

    @staticmethod
    def _paragraph_count(body: str) -> int:
        return len([part for part in re.split(r"\n\s*\n", body) if part.strip()])

    @staticmethod
    def _log_api_failure(story: Story, endpoint: str, reason: str) -> None:
        LOGGER.debug(
            "Sport article API source=%s url=%s endpoint=%s "
            "structure=rejected fallback_failure=%s",
            story.source,
            story.url,
            SportArticleService._endpoint_for_log(endpoint),
            reason,
        )

    def _default_article_scraper_factory(self) -> ArticleScraper:
        return ArticleScraper(timeout=self.timeout)

    @staticmethod
    def _store_failure(
        story: Story,
        error: str,
    ) -> None:
        story.extras.update(
            {
                "article_content_status": "failed",
                "article_content_error": str(error or "").strip(),
            }
        )

    @staticmethod
    def _validate_story(story: Story) -> None:
        if not isinstance(story, Story):
            raise TypeError(
                f"Expected Story, received {type(story).__name__}."
            )

    @staticmethod
    def _normalise_text(value: Any) -> str:
        return " ".join(str(value or "").split()).strip()

    @classmethod
    def _clean_list(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            source = re.split(r"[,|]", value)
        elif isinstance(value, (list, tuple, set)):
            source = value
        else:
            source = []

        result: list[str] = []

        for item in source:
            cleaned = cls._normalise_text(item)
            if cleaned and cleaned not in result:
                result.append(cleaned)

        return result

    @classmethod
    def _merge_unique(
        cls,
        existing: list[str],
        incoming: list[str],
    ) -> list[str]:
        result: list[str] = []

        for value in [*existing, *incoming]:
            cleaned = cls._normalise_text(value)
            if cleaned and cleaned not in result:
                result.append(cleaned)

        return result


__all__ = [
    "SportArticleResult",
    "SportArticleService",
]
