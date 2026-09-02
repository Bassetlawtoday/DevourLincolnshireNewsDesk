"""Non-UI orchestration for the Sport Source Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from newsdesk.sports.source_manager.validator import (
    LIST_FIELDS,
    SourceValidation,
    SourceValidator,
)
from newsdesk.sports.websites import GenericWebsiteScraper, WebsiteSource
from newsdesk.sports.websites.loader import DEFAULT_CONFIG_PATH
from newsdesk.services.sport_article_service import SportArticleService
from newsdesk.sources.base_scraper import ScrapeResponse


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SourcePreview:
    title: str
    published: str
    url: str
    image_available: bool
    summary_available: bool
    current: bool
    discovery_score: int
    warning: str = ""


@dataclass(slots=True)
class SourceAnalysis:
    status: str = "Not ready"
    resolved_url: str = ""
    http_status: int = 0
    redirect_count: int = 0
    content_type: str = ""
    response_seconds: float = 0.0
    tls_validated: bool = False
    page_type: str = "unknown"
    links_examined: int = 0
    candidates_discovered: int = 0
    candidates_accepted: int = 0
    candidates_rejected: int = 0
    duplicates_removed: int = 0
    current_stories: int = 0
    warnings: list[str] = field(default_factory=list)
    suggestions: dict[str, Any] = field(default_factory=dict)
    preview: list[SourcePreview] = field(default_factory=list)
    error: str = ""


class SourceManagerService:
    """Validate, test and atomically persist Generic Website definitions."""

    RESPONSE_LIMIT = 5 * 1024 * 1024
    MAX_REDIRECTS = 5
    PREVIEW_LIMIT = 10

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH)
        self.validator = SourceValidator()
        self._tested_fingerprint = ""
        self._preview_stories: dict[str, Any] = {}

    def load_definitions(self) -> list[dict[str, Any]]:
        payload = self._read_payload()
        definitions = payload.get("sources", [])
        result: list[dict[str, Any]] = []
        for raw in definitions:
            item = dict(raw)
            item.setdefault("enabled", True)
            item.setdefault("source_id", self._derived_id(item))
            result.append(item)
        return result

    def validate(
        self,
        values: dict[str, Any],
        *,
        current_id: str = "",
        resolve_dns: bool = False,
    ) -> SourceValidation:
        return self.validator.validate(
            values,
            self.load_definitions(),
            current_id=current_id,
            resolve_dns=resolve_dns,
        )

    def test_source(
        self,
        values: dict[str, Any],
        *,
        current_id: str = "",
    ) -> SourceAnalysis:
        self._tested_fingerprint = ""
        validation = self.validate(
            values,
            current_id=current_id,
            resolve_dns=True,
        )
        if not validation.valid:
            return SourceAnalysis(error="; ".join(validation.errors))

        source_dict = self.normalise_definition(values)
        source = WebsiteSource.from_dict(source_dict)
        analysis = SourceAnalysis()
        try:
            response, html = self._probe(source)
            analysis.resolved_url = response.url
            analysis.http_status = response.status_code
            analysis.redirect_count = len(response.history)
            analysis.content_type = response.headers.get("Content-Type", "")
            analysis.response_seconds = response.elapsed.total_seconds()
            analysis.tls_validated = response.url.startswith("https://")
            soup = BeautifulSoup(html, "html.parser")
            hrefs = [str(anchor.get("href") or "") for anchor in soup.find_all("a", href=True)]
            analysis.links_examined = min(len(hrefs), 2000)
            analysis.duplicates_removed = max(0, len(hrefs) - len(set(hrefs)))
            analysis.page_type = self._page_type(source.listing_url, response.url, soup)
            if analysis.links_examined == 0 and len(soup.find_all("script")) >= 3:
                analysis.warnings.append(
                    "Client-side rendering detected; advanced configuration may be required."
                )
            if re.search(
                r"(?:news|content)\.cms\.|content[_-]?api",
                html,
                flags=re.IGNORECASE,
            ):
                analysis.warnings.append("A potential first-party content API was detected.")
            if analysis.page_type == "homepage":
                analysis.warnings.append("URL appears to be a homepage.")
                suggestions = self._news_link_suggestions(response.url, soup)
                if suggestions:
                    analysis.suggestions["listing_urls"] = suggestions

            scraper = GenericWebsiteScraper(source)
            parse_response = ScrapeResponse(
                url=response.url,
                body=html,
                status_code=response.status_code,
                content_type=analysis.content_type,
            )
            content_api_url = str(
                source.metadata.get("content_api_url", "") or ""
            ).strip()
            if content_api_url:
                api_source = WebsiteSource(
                    name=source.name,
                    sport=source.sport,
                    listing_url=content_api_url,
                    timeout=source.timeout,
                    headers=source.headers,
                )
                api_response, api_body = self._probe(api_source)
                parse_response = ScrapeResponse(
                    url=api_response.url,
                    body=api_body,
                    status_code=api_response.status_code,
                    content_type=api_response.headers.get("Content-Type", ""),
                )
            stories = list(scraper.parse(parse_response))
            analysis.candidates_discovered = scraper._last_candidate_count
            analysis.candidates_accepted = len(stories)
            analysis.candidates_rejected = max(
                0,
                analysis.candidates_discovered - len(stories),
            )
            analysis.current_stories = len(stories)
            analysis.preview = [
                SourcePreview(
                    title=story.title,
                    published=story.published,
                    url=story.url,
                    image_available=bool(story.image_url),
                    summary_available=bool(story.summary),
                    current=True,
                    discovery_score=scraper._discovery_scores.get(story.url, 0),
                )
                for story in stories[: self.PREVIEW_LIMIT]
            ]
            self._preview_stories = {story.url: story for story in stories}
            self._add_discovery_warnings(analysis)
            analysis.suggestions.update(self._configuration_suggestions(source, soup, stories))
            analysis.warnings.extend(validation.warnings)
            analysis.status = (
                "Ready to save"
                if stories and not analysis.warnings
                else "Ready with warnings"
                if stories
                else "Not ready"
            )
            if stories:
                self._tested_fingerprint = self.fingerprint(source_dict)
        except Exception as error:
            LOGGER.exception("Sport source test failed for %s", source.name)
            analysis.error = str(error)
            if "403" in analysis.error:
                analysis.warnings.append("Access blocked with HTTP 403.")
            elif "401" in analysis.error:
                analysis.warnings.append("Authentication appears to be required.")
            elif "certificate" in analysis.error.casefold() or "ssl" in analysis.error.casefold():
                analysis.warnings.append("TLS certificate validation failed.")
        return analysis

    def test_preview_article(self, url: str) -> dict[str, Any]:
        """Run the explicit one-story deep extraction requested by the editor."""

        story = self._preview_stories.get(str(url or "").strip())
        if story is None:
            raise KeyError("Select a story from the latest preview first.")
        result = SportArticleService(timeout=25.0).enrich(story)
        return {
            "successful": result.successful,
            "word_count": result.word_count,
            "summary": story.summary,
            "image_url": story.image_url,
            "image_local_path": story.image_local_path,
            "image_available": bool(story.image_local_path),
            "extraction_source": story.extras.get(
                "article_content_extraction_source",
                "none",
            ),
            "error": result.error,
        }

    def save_source(
        self,
        values: dict[str, Any],
        *,
        current_id: str = "",
    ) -> tuple[dict[str, Any], Path]:
        definition = self.normalise_definition(values)
        validation = self.validate(definition, current_id=current_id)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        if self.fingerprint(definition) != self._tested_fingerprint:
            raise RuntimeError("Test Source must succeed before saving changes.")

        definitions = self.load_definitions()
        source_id = current_id or str(definition.get("source_id") or self._derived_id(definition))
        definition["source_id"] = source_id
        replaced = False
        for index, existing in enumerate(definitions):
            if str(existing.get("source_id")) == source_id:
                definitions[index] = definition
                replaced = True
                break
        if current_id and not replaced:
            raise KeyError(f"Source {current_id!r} no longer exists.")
        if not replaced:
            definitions.append(definition)
        backup = self._atomic_write(definitions)
        self._tested_fingerprint = self.fingerprint(definition)
        return definition, backup

    def delete_source(self, source_id: str) -> Path:
        definitions = self.load_definitions()
        target = next(
            (item for item in definitions if item.get("source_id") == source_id),
            None,
        )
        if target is not None and target.get("managed_by") != "newsroom":
            raise PermissionError(
                "Built-in and preconfigured sources can be disabled but not deleted."
            )
        retained = [item for item in definitions if item.get("source_id") != source_id]
        if len(retained) == len(definitions):
            raise KeyError(source_id)
        self._tested_fingerprint = ""
        return self._atomic_write(retained)

    def normalise_definition(self, values: dict[str, Any]) -> dict[str, Any]:
        result = dict(values)
        for key in LIST_FIELDS:
            result[key] = self.validator._list(result.get(key))
            if not result[key]:
                result.pop(key, None)
        result["name"] = str(result.get("name") or "").strip()
        result["organisation"] = str(result.get("organisation") or result["name"]).strip()
        result["listing_url"] = str(result.get("listing_url") or "").strip()
        result["sport"] = str(result.get("sport") or "Football").strip()
        result["location"] = str(result.get("location") or "Lincolnshire").strip()
        result["max_stories"] = int(result.get("max_stories", 20))
        result["enabled"] = bool(result.get("enabled", True))
        for key in ("listing_warmup_url", "content_api_url", "content_api_item_path"):
            value = str(result.pop(key, "") or "").strip()
            if value:
                result[key] = value
        return {key: value for key, value in result.items() if value not in (None, "")}

    @staticmethod
    def fingerprint(definition: dict[str, Any]) -> str:
        data = json.dumps(definition, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _probe(self, source: WebsiteSource) -> tuple[requests.Response, str]:
        session = requests.Session()
        target = source.listing_url
        history: list[requests.Response] = []
        response: requests.Response | None = None
        for _redirect in range(self.MAX_REDIRECTS + 1):
            safety_errors = self.validator._url_errors(target, resolve_dns=True)
            if safety_errors:
                raise ValueError("Unsafe request destination: " + "; ".join(safety_errors))
            response = session.get(
                target,
                headers={"User-Agent": GenericWebsiteScraper.DEFAULT_USER_AGENT},
                timeout=source.timeout,
                stream=True,
                allow_redirects=False,
            )
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location", "")
                if not location:
                    raise ValueError("Redirect response did not provide a destination.")
                history.append(response)
                target = urljoin(target, location)
                continue
            break
        else:
            raise ValueError("Source exceeded the five-redirect safety limit.")
        if response is None:
            raise ValueError("Source returned no response.")
        response.history = history
        response.raise_for_status()
        final_errors = self.validator._url_errors(response.url, resolve_dns=True)
        if final_errors:
            raise ValueError("Unsafe redirect destination: " + "; ".join(final_errors))
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > self.RESPONSE_LIMIT:
                raise ValueError("Response exceeded the 5 MB safety limit.")
            chunks.append(chunk)
        return response, b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    @staticmethod
    def _page_type(entered: str, resolved: str, soup: BeautifulSoup) -> str:
        path = urlparse(resolved).path.rstrip("/")
        content_type = str(getattr(soup, "original_encoding", "") or "")
        if not path:
            return "homepage"
        if re.search(r"/(news|latest|blog|articles?|stories)(/|$)", path, re.I):
            return "listing page"
        if soup.find("rss") or "xml" in content_type:
            return "feed"
        if soup.find("article") and len(soup.find_all("article")) == 1:
            return "article page"
        return "website page"

    @staticmethod
    def _news_link_suggestions(base_url: str, soup: BeautifulSoup) -> list[str]:
        pattern = re.compile(r"^(?:latest news|club news|news|updates|stories|articles|blog)$", re.I)
        suggestions: list[str] = []
        for anchor in soup.find_all("a", href=True):
            label = " ".join(anchor.get_text(" ", strip=True).split())
            if pattern.match(label):
                candidate = urljoin(base_url, anchor["href"])
                if candidate not in suggestions:
                    suggestions.append(candidate)
        return suggestions[:8]

    @staticmethod
    def _configuration_suggestions(
        source: WebsiteSource,
        soup: BeautifulSoup,
        stories: list[Any],
    ) -> dict[str, Any]:
        suggestions: dict[str, Any] = {}
        if stories:
            suggestions["include_url_patterns"] = [
                re.escape(urlparse(source.listing_url).netloc) + r"/.+"
            ]
            suggestions["tags"] = list(
                dict.fromkeys(
                    [source.sport, source.location, *source.tags]
                )
            )
            suggestions["location"] = source.location
        if soup.select("article a[href]"):
            suggestions["article_link_selectors"] = ["article a[href]"]
            suggestions["card_selectors"] = ["article"]
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if title and source.organisation == source.name:
            suggestions["organisation"] = re.split(r"[|â€“—-]", title)[0].strip()
        return suggestions

    @staticmethod
    def _add_discovery_warnings(analysis: SourceAnalysis) -> None:
        if analysis.candidates_discovered == 0:
            analysis.warnings.append("No article links were found.")
        if analysis.candidates_discovered and analysis.current_stories == 0:
            analysis.warnings.append("No stories survived the 3-day date rule.")
        if analysis.preview and not any(item.image_available for item in analysis.preview):
            analysis.warnings.append("Images are unavailable in detected cards.")
        if analysis.preview and not any(item.summary_available for item in analysis.preview):
            analysis.warnings.append("Summaries are unavailable in detected cards.")
        if analysis.links_examined > 1000:
            analysis.warnings.append("The page contains an excessive number of links.")

    def _atomic_write(self, definitions: list[dict[str, Any]]) -> Path:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        backup = self.config_path.with_name(
            f"{self.config_path.name}.{datetime.now(timezone.utc):%Y%m%d%H%M%S%f}.bak"
        )
        if self.config_path.exists():
            shutil.copy2(self.config_path, backup)
        payload = {"version": 1, "sources": definitions}
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
            dir=self.config_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.config_path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return backup

    def _read_payload(self) -> dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return {"version": 1, "sources": payload}
        if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
            raise ValueError("Invalid Sport website source configuration.")
        return payload

    @staticmethod
    def _derived_id(definition: dict[str, Any]) -> str:
        seed = "|".join(
            (
                str(definition.get("name") or "").strip().casefold(),
                SourceValidator.normalise_url(definition.get("listing_url", "")),
            )
        )
        slug = re.sub(r"[^a-z0-9]+", "-", str(definition.get("name") or "source").casefold()).strip("-")
        return f"{slug or 'source'}-{hashlib.sha256(seed.encode()).hexdigest()[:10]}"


__all__ = ["SourceAnalysis", "SourceManagerService", "SourcePreview", "SourceValidation"]
