"""
newsdesk.sources.base_scraper

Shared scraper foundation for Devour Lincolnshire NewsDesk.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from newsdesk.publish_result import PublishResult
from newsdesk.story import Story
from newsdesk.story_engine import StoryEngine


LOGGER = logging.getLogger(__name__)


class ScraperError(RuntimeError):
    """
    Base exception for scraper failures.
    """


class ScraperRequestError(ScraperError):
    """
    Raised when a webpage cannot be downloaded.
    """


class ScraperParseError(ScraperError):
    """
    Raised when downloaded content cannot be parsed.
    """


@dataclass(slots=True)
class ScrapeResponse:
    """
    Normalised HTTP response returned by fetch().
    """

    url: str
    body: str
    status_code: int
    content_type: str = ""
    encoding: str = "utf-8"
    headers: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass(slots=True)
class ScrapeReport:
    """
    Summary of the most recent scraper run.
    """

    source_name: str
    source_url: str
    stories_found: int = 0
    stories_processed: int = 0
    stories_rejected: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None

    @property
    def successful(self) -> bool:
        return not self.errors

    @property
    def duration_seconds(self) -> float:
        if self.completed_at is None:
            return 0.0

        return max(
            0.0,
            (self.completed_at - self.started_at).total_seconds(),
        )


class BaseScraper(ABC):
    """
    Base class for NewsDesk source scrapers.

    Subclasses must implement parse() and return Story objects.
    """

    DEFAULT_TIMEOUT = 30.0

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0 Safari/537.36 "
        "BassetlawToday-NewsDesk/1.0"
    )

    def __init__(
        self,
        *,
        source_name: str,
        source_url: str,
        engine: StoryEngine | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        request_delay: float = 0.0,
        user_agent: str = DEFAULT_USER_AGENT,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        source_name = source_name.strip()
        source_url = source_url.strip()

        if not source_name:
            raise ValueError("source_name cannot be empty.")

        if not source_url:
            raise ValueError("source_url cannot be empty.")

        if timeout <= 0:
            raise ValueError("timeout must be greater than zero.")

        if request_delay < 0:
            raise ValueError(
                "request_delay cannot be negative."
            )

        self.source_name = source_name
        self.source_url = source_url
        self.engine = engine or StoryEngine()
        self.timeout = float(timeout)
        self.request_delay = float(request_delay)
        self.user_agent = user_agent.strip()
        self.extra_headers = dict(extra_headers or {})

        self._stories: list[Story] = []
        self._results: list[PublishResult] = []
        self._last_response: ScrapeResponse | None = None
        self._last_report: ScrapeReport | None = None

    def fetch(
        self,
        url: str | None = None,
    ) -> ScrapeResponse:
        """
        Download a webpage and return a ScrapeResponse.
        """

        target_url = (url or self.source_url).strip()

        if not target_url:
            raise ValueError("A target URL is required.")

        if self.request_delay:
            time.sleep(self.request_delay)

        request = Request(
            target_url,
            headers=self._build_headers(),
            method="GET",
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                raw_body = response.read()

                status_code = int(
                    getattr(response, "status", 200)
                )

                content_type = (
                    response.headers.get_content_type()
                    or ""
                )

                encoding = (
                    response.headers.get_content_charset()
                    or "utf-8"
                )

                headers = {
                    str(key): str(value)
                    for key, value in response.headers.items()
                }

                body = raw_body.decode(
                    encoding,
                    errors="replace",
                )

        except HTTPError as error:
            raise ScraperRequestError(
                f"{self.source_name} returned HTTP "
                f"{error.code} for {target_url}."
            ) from error

        except URLError as error:
            reason = getattr(error, "reason", error)

            raise ScraperRequestError(
                f"Could not connect to {self.source_name}: "
                f"{reason}"
            ) from error

        except TimeoutError as error:
            raise ScraperRequestError(
                f"Request to {self.source_name} timed out."
            ) from error

        except OSError as error:
            raise ScraperRequestError(
                f"Could not download {target_url}: {error}"
            ) from error

        scrape_response = ScrapeResponse(
            url=target_url,
            body=body,
            status_code=status_code,
            content_type=content_type,
            encoding=encoding,
            headers=headers,
        )

        self._last_response = scrape_response

        return scrape_response

    @abstractmethod
    def parse(
        self,
        response: ScrapeResponse,
    ) -> Iterable[Story]:
        """
        Parse a downloaded response and return Story objects.
        """

        raise NotImplementedError

    def get_stories(
        self,
        *,
        refresh: bool = True,
        deduplicate: bool = True,
    ) -> list[Story]:
        """
        Download and parse stories from the source.
        """

        if not refresh and self._stories:
            return list(self._stories)

        report = ScrapeReport(
            source_name=self.source_name,
            source_url=self.source_url,
        )

        try:
            response = self.fetch()
            parsed = list(self.parse(response))
            stories = self._normalise_stories(parsed)

            if deduplicate:
                stories = self._deduplicate_stories(stories)

            self._stories = stories
            report.stories_found = len(stories)

        except ScraperError:
            raise

        except Exception as error:
            LOGGER.exception(
                "Could not parse stories from %s.",
                self.source_name,
            )

            raise ScraperParseError(
                f"Could not parse stories from "
                f"{self.source_name}: {error}"
            ) from error

        finally:
            report.completed_at = datetime.now(timezone.utc)
            self._last_report = report

        return list(self._stories)

    def process(
        self,
        stories: Iterable[Story] | None = None,
        *,
        refresh: bool = True,
        continue_on_error: bool = True,
    ) -> list[PublishResult]:
        """
        Process stories through StoryEngine.
        """

        source_stories = (
            list(stories)
            if stories is not None
            else self.get_stories(refresh=refresh)
        )

        report = ScrapeReport(
            source_name=self.source_name,
            source_url=self.source_url,
            stories_found=len(source_stories),
        )

        results: list[PublishResult] = []

        for index, story in enumerate(
            source_stories,
            start=1,
        ):
            try:
                result = self.engine.process(story)
                results.append(result)

            except Exception as error:
                report.stories_rejected += 1

                identifier = (
                    story.title.strip()
                    or story.url.strip()
                    or f"Story {index}"
                )

                report.errors.append(
                    f"{identifier}: {error}"
                )

                LOGGER.exception(
                    "Could not process %s.",
                    identifier,
                )

                if not continue_on_error:
                    report.completed_at = datetime.now(timezone.utc)
                    self._last_report = report
                    raise

        report.stories_processed = len(results)
        report.completed_at = datetime.now(timezone.utc)

        self._results = results
        self._last_report = report

        return list(results)

    def run(
        self,
        *,
        refresh: bool = True,
        continue_on_error: bool = True,
    ) -> list[PublishResult]:
        """
        Download, parse and process the source.
        """

        return self.process(
            refresh=refresh,
            continue_on_error=continue_on_error,
        )

    def clear(self) -> None:
        """
        Clear all cached scraper data.
        """

        self._stories.clear()
        self._results.clear()
        self._last_response = None
        self._last_report = None

    @property
    def stories(self) -> list[Story]:
        return list(self._stories)

    @property
    def publish_results(self) -> list[PublishResult]:
        return list(self._results)

    @property
    def last_response(self) -> ScrapeResponse | None:
        return self._last_response

    @property
    def last_report(self) -> ScrapeReport | None:
        return self._last_report

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-GB,en;q=0.9",
            "Cache-Control": "no-cache",
        }

        headers.update(self.extra_headers)

        return headers

    def _normalise_stories(
        self,
        stories: Iterable[Story],
    ) -> list[Story]:
        normalised: list[Story] = []
        scraped_at = datetime.now(timezone.utc)

        for item in stories:
            if not isinstance(item, Story):
                raise ScraperParseError(
                    f"{self.source_name}.parse() returned "
                    f"{type(item).__name__}; expected Story."
                )

            if not item.source.strip():
                item.source = self.source_name

            if item.scraped_at is None:
                item.scraped_at = scraped_at

            normalised.append(item)

        return normalised

    @staticmethod
    def _deduplicate_stories(
        stories: Iterable[Story],
    ) -> list[Story]:
        unique: list[Story] = []
        seen: set[str] = set()

        for story in stories:
            key = BaseScraper._story_key(story)

            if key in seen:
                continue

            seen.add(key)
            unique.append(story)

        return unique

    @staticmethod
    def _story_key(story: Story) -> str:
        story_id = str(
            story.story_id or ""
        ).strip().lower()

        if story_id:
            return f"id:{story_id}"

        url = story.url.strip().lower().rstrip("/")

        if url:
            return f"url:{url}"

        title = " ".join(
            story.title.lower().split()
        )

        published = str(
            story.published or ""
        ).strip().lower()

        return f"title:{title}|published:{published}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"source_name={self.source_name!r}, "
            f"source_url={self.source_url!r})"
        )


__all__ = [
    "BaseScraper",
    "ScrapeReport",
    "ScrapeResponse",
    "ScraperError",
    "ScraperParseError",
    "ScraperRequestError",
]