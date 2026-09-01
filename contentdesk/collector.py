"""Headless, API-key authenticated collector for the LDRS Content Explorer."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import time
from urllib.parse import urljoin, urlsplit

from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait


class ContentExplorerError(RuntimeError):
    """Safe user-facing collection failure."""


_LABELS = {
    "type": "content_type",
    "author": "author",
    "author's email": "author_email",
    "last reviewed by email": "reviewer_email",
    "created at": "created_at",
    "modified at": "modified_at",
}


def _article_id(url: str) -> str:
    match = re.search(r"/article/(\d+)", str(url or ""))
    return match.group(1) if match else ""


def _normalise_date(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = re.sub(r"\s*\([^)]*GMT\)\s*$", "", raw).strip()
    for pattern in ("%a, %b %d, %Y %H:%M", "%a, %d %b %Y %H:%M"):
        try:
            return datetime.strptime(candidate, pattern).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return raw


def _credit_from_caption(value: str) -> str:
    match = re.search(r"\bCredit:\s*(.+)$", str(value or ""), flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


_DETAIL_UI_LINES = {
    "advanced search", "all", "story", "advisory", "download text",
    "download images", "log out",
}


def _detail_body_lines(lines: list[str], title: str, categories_marker: int) -> list[str]:
    """Return article copy without Content Explorer account/navigation chrome."""
    boundary = max(0, int(categories_marker))
    candidates = list(lines[:boundary])
    download_indexes = [
        index for index, line in enumerate(candidates)
        if line.casefold() == "download text"
    ]
    if download_indexes:
        candidates = candidates[download_indexes[-1] + 1:]
    excluded_prefixes = (
        "slug:", "by:", "author's email:", "last reviewed by email:",
        "created at:", "modified at:",
    )
    cleaned: list[str] = []
    for line in candidates:
        folded = line.casefold().strip()
        if not folded or folded in _DETAIL_UI_LINES:
            continue
        if folded.startswith(excluded_prefixes):
            continue
        if title and folded == title.casefold().strip():
            continue
        if re.match(r"^[A-Z][a-z]{2},\s+[A-Z][a-z]{2}\s+\d", line):
            continue
        if folded.endswith(" log out"):
            continue
        cleaned.append(line)
    return cleaned


def _split_authorities(values: list[str]) -> list[str]:
    """Separate adjacent LDRS authority chips flattened by Selenium text."""
    pattern = re.compile(
        r"(?:[A-Z][A-Za-z&'’.-]*(?:\s+(?:of|the|upon|on|and|North|South|East|West|"
        r"[A-Z][A-Za-z&'’.-]*))*?\s+(?:County Council|City Council|District Council|"
        r"Borough Council|Combined Authority|Council))"
    )
    result: list[str] = []
    for value in values:
        matches = pattern.findall(str(value or "").strip())
        candidates = matches or ([str(value).strip()] if str(value).strip() else [])
        for candidate in candidates:
            if candidate not in result:
                result.append(candidate)
    return result


def _parse_listing_text(text: str, url: str) -> dict:
    lines = [" ".join(line.split()) for line in str(text or "").splitlines() if line.strip()]
    flat = " ".join(lines)
    story = {
        "article_id": _article_id(url), "source_url": url, "content_type": "Story",
        "title": lines[0] if lines else "", "slug": "", "summary": "", "body": "",
        "author": "", "author_email": "", "reviewer_email": "", "created_at": "",
        "modified_at": "", "authorities": [], "categories": [], "image_url": "",
        "image_caption": "", "image_credit": "", "detail_complete": False,
    }
    # Content Explorer currently renders several card fields on the same visual
    # line.  Parse the labelled boundaries from the flattened card as well as
    # supporting the older one-label-per-line representation.
    explorer_date = r"[A-Z][a-z]{2},\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}(?:\s+\([^)]*GMT\))?"
    created = re.search(rf"\bCreated at:\s*({explorer_date})", flat, re.I)
    modified = re.search(rf"\bModified at:\s*({explorer_date})", flat, re.I)
    identity = re.search(
        r"\b(Story|Advisory)\s+Author:\s*(.+?)\s+Author's email:\s*(\S+)\s+"
        r"Last reviewed by email:\s*(\S+)", flat, re.I,
    )
    if created:
        story["created_at"] = _normalise_date(created.group(1))
    if modified:
        story["modified_at"] = _normalise_date(modified.group(1))
    if identity:
        story["content_type"] = identity.group(1).title()
        story["author"] = identity.group(2).strip()
        story["author_email"] = identity.group(3).strip()
        story["reviewer_email"] = identity.group(4).strip()

    label_index = len(lines)
    for index, line in enumerate(lines):
        lowered = line.casefold()
        for label, field in _LABELS.items():
            prefix = f"{label}:"
            if lowered.startswith(prefix):
                label_index = min(label_index, index)
                value = line[len(prefix):].strip()
                # Do not replace a field already extracted from a reliable
                # same-line boundary with a concatenated visual value.
                if not story[field]:
                    story[field] = _normalise_date(value) if field.endswith("_at") else value
                break
    preamble = lines[1:label_index]
    if preamble:
        story["slug"] = re.sub(r"\s+v\.\d+$", "", preamble[0], flags=re.IGNORECASE).strip()
        story["summary"] = "\n\n".join(preamble[1:]).strip()
    metadata_end = max(
        (index for index, line in enumerate(lines) if any(line.casefold().startswith(f"{label}:") for label in _LABELS)),
        default=label_index - 1,
    )
    story["authorities"] = _split_authorities([line for line in lines[metadata_end + 1:] if line])
    if identity:
        # In the current card, authority chips sit between the date metadata
        # and the combined "Story Author" metadata line.
        identity_line = next((i for i, line in enumerate(lines) if re.search(r"\b(?:Story|Advisory)\s+Author:", line, re.I)), -1)
        modified_line = next((i for i, line in enumerate(lines) if "modified at:" in line.casefold()), -1)
        if identity_line > modified_line >= 0:
            candidates = lines[modified_line + 1:identity_line]
            story["authorities"] = _split_authorities(
                [line for line in candidates if not re.search(r"\b(?:created|modified) at:", line, re.I)]
            )
    return story


class ContentExplorerCollector:
    BASE_URL = "https://ldrs.org.uk"

    def __init__(self, api_key: str, *, base_url: str = BASE_URL, headless: bool = True, timeout: int = 25):
        self.api_key = str(api_key or "").strip()
        self.base_url = str(base_url or self.BASE_URL).rstrip("/")
        self.headless = bool(headless)
        self.timeout = max(10, int(timeout))
        self._driver: WebDriver | None = None

    def _options(self) -> Options:
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        for argument in (
            "--disable-gpu", "--disable-notifications", "--disable-popup-blocking",
            "--disable-dev-shm-usage", "--no-sandbox", "--log-level=3",
            "--window-size=1600,1100",
        ):
            options.add_argument(argument)
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        return options

    def _driver_instance(self) -> WebDriver:
        if self._driver is not None:
            try:
                _ = self._driver.current_url
                return self._driver
            except (NoSuchWindowException, WebDriverException):
                self._driver = None
        try:
            self._driver = webdriver.Chrome(options=self._options())
            self._driver.set_page_load_timeout(self.timeout)
            return self._driver
        except WebDriverException as exc:
            raise ContentExplorerError(
                "Chrome could not start for Content Explorer. Confirm Chrome and Selenium are installed."
            ) from exc

    def close(self) -> None:
        driver, self._driver = self._driver, None
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def login(self) -> None:
        if not self.api_key:
            raise ContentExplorerError("Add the LDRS API key in API SETTINGS before updating content.")
        driver = self._driver_instance()
        driver.get(self.base_url + "/")
        wait = WebDriverWait(driver, self.timeout)
        try:
            input_box = wait.until(
                lambda d: next((element for element in d.find_elements(By.CSS_SELECTOR, 'input[placeholder="api key"]') if element.is_displayed()), None)
            )
            input_box.clear()
            input_box.send_keys(self.api_key)
            buttons = driver.find_elements(By.XPATH, "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'log in')]")
            if buttons:
                buttons[0].click()
            else:
                input_box.send_keys(Keys.ENTER)
            wait.until(lambda d: any("log out" in element.text.casefold() for element in d.find_elements(By.TAG_NAME, "button")))
        except TimeoutException as exc:
            message = "Content Explorer rejected the API key or did not complete sign-in."
            raise ContentExplorerError(message) from exc

    def test_connection(self) -> dict:
        try:
            self.login()
            name = ""
            for element in self._driver_instance().find_elements(By.CSS_SELECTOR, "nav"):
                text = " ".join(element.text.split())
                if "Log Out" in text or "Log out" in text:
                    name = text.replace("Log Out", "").replace("Log out", "").strip()
                    break
            return {"ok": True, "account": name}
        finally:
            self.close()

    def collect_listings(self, *, limit: int | None = 500, on_progress=None) -> list[dict]:
        self.login()
        driver = self._driver_instance()
        driver.get(self.base_url + "/explorer/story")
        wait = WebDriverWait(driver, self.timeout)
        try:
            wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'a[href*="/article/"]')) > 0)
        except TimeoutException as exc:
            raise ContentExplorerError("Content Explorer returned no Story records.") from exc

        target = None if limit is None else max(1, int(limit))
        previous = -1
        while True:
            links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/article/"]')
            unique_count = len({_article_id(link.get_attribute("href")) for link in links})
            if on_progress:
                on_progress(f"Discovered {unique_count:,} LDRS stories…")
            if target is not None and unique_count >= target:
                break
            show_more = [element for element in driver.find_elements(By.XPATH, "//*[self::a or self::button][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'show more')]") if element.is_displayed()]
            if not show_more or unique_count == previous:
                break
            previous = unique_count
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", show_more[0])
            show_more[0].click()
            try:
                WebDriverWait(driver, 8).until(
                    lambda d: len({_article_id(link.get_attribute("href")) for link in d.find_elements(By.CSS_SELECTOR, 'a[href*="/article/"]')}) > previous
                )
            except TimeoutException:
                break

        stories: dict[str, dict] = {}
        for link in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/article/"]'):
            url = str(link.get_attribute("href") or "").strip()
            article_id = _article_id(url)
            if not article_id or article_id in stories:
                continue
            record = _parse_listing_text(link.text, url)
            image_elements = link.find_elements(By.TAG_NAME, "img")
            if image_elements:
                record["image_url"] = str(image_elements[0].get_attribute("src") or "").strip()
            stories[article_id] = record
            if target is not None and len(stories) >= target:
                break
        return list(stories.values())

    def fetch_detail(self, article_id: str) -> dict:
        self.login()
        driver = self._driver_instance()
        url = urljoin(self.base_url + "/", f"article/{str(article_id).strip()}")
        driver.get(url)
        wait = WebDriverWait(driver, self.timeout)
        try:
            wait.until(lambda d: "Categories:" in d.find_element(By.TAG_NAME, "body").text)
        except TimeoutException as exc:
            raise ContentExplorerError("The full LDRS story did not finish loading.") from exc
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        title = ""
        headings = driver.find_elements(By.TAG_NAME, "h1")
        if headings:
            title = headings[0].text.strip()
        record = {
            "article_id": _article_id(url), "source_url": url, "title": title,
            "content_type": "Story", "slug": "", "summary": "", "body": "",
            "author": "", "author_email": "", "reviewer_email": "", "created_at": "",
            "modified_at": "", "authorities": [], "categories": [], "image_url": "",
            "image_caption": "", "image_credit": "", "detail_complete": True,
        }
        for line in lines:
            lowered = line.casefold()
            if lowered.startswith("slug:"):
                record["slug"] = re.sub(r"\s+v\.\d+$", "", line[5:].strip(), flags=re.IGNORECASE)
            elif lowered.startswith("by:"):
                record["author"] = line[3:].strip()
            elif lowered.startswith("author's email:"):
                record["author_email"] = line.split(":", 1)[1].strip()
            elif lowered.startswith("last reviewed by email:"):
                record["reviewer_email"] = line.split(":", 1)[1].strip()
            elif lowered.startswith("categories:"):
                category_text = line.split(":", 1)[1].strip()
                record["categories"] = [category_text] if category_text else []

        images = []
        for image in driver.find_elements(By.CSS_SELECTOR, 'img[src*="ldrs-media-assets"]'):
            src = str(image.get_attribute("src") or "").split("?", 1)[0]
            if src and src not in images:
                images.append(src)
        record["image_url"] = images[0] if images else ""

        attachment_marker = next((i for i, line in enumerate(lines) if line.casefold() == "attachments preview"), -1)
        categories_marker = next((i for i, line in enumerate(lines) if line.casefold().startswith("categories:")), len(lines))
        detail_start = 0
        if attachment_marker >= 0:
            detail_start = attachment_marker + 1
            credit_indexes = [
                index for index in range(detail_start, categories_marker)
                if "credit:" in lines[index].casefold()
            ]
            caption_lines = [lines[index] for index in credit_indexes]
            if credit_indexes:
                detail_start = credit_indexes[-1] + 1
            while detail_start < categories_marker and lines[detail_start].casefold() in {"download text", "download images"}:
                detail_start += 1
            if caption_lines:
                record["image_caption"] = caption_lines[0]
                record["image_credit"] = _credit_from_caption(caption_lines[0])
        body_lines = _detail_body_lines(lines[detail_start:categories_marker], title, categories_marker - detail_start)
        record["body"] = "\n\n".join(body_lines).strip()
        record["summary"] = record["body"].split("\n\n", 1)[0] if record["body"] else record["slug"]

        date_lines = [line for line in lines if re.match(r"^[A-Z][a-z]{2},\s+[A-Z][a-z]{2}\s+\d", line)]
        if date_lines:
            record["created_at"] = _normalise_date(date_lines[0])
            record["modified_at"] = record["created_at"]
        return record

    def open_article_visible(self, article_id: str) -> str:
        """Open a visible authenticated Content Explorer window at one article."""
        self.login()
        url = urljoin(self.base_url + "/", f"article/{str(article_id).strip()}")
        self._driver_instance().get(url)
        return url


__all__ = ["ContentExplorerCollector", "ContentExplorerError", "_detail_body_lines", "_parse_listing_text"]
