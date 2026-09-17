"""Isolated collectors for supported non-Idox Lincolnshire planning sources."""

from __future__ import annotations

from io import BytesIO
from datetime import date, timedelta
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from services.models import PlanningApplication
from services.planning_sources import PlanningSource


_REFERENCE = re.compile(r"\bH\d{2}-\d{4}-\d{2}\b", re.IGNORECASE)
_DATE = re.compile(r"\b\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\b")


def _clean(value: str) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())


def lincolnshire_county_seven_day_url(
    source: PlanningSource,
    *,
    search_type: str,
) -> str:
    """Build the county register's official rolling seven-day search URL."""
    normalised = str(search_type or "").strip().title()
    if normalised not in {"Received", "Decided"}:
        raise ValueError("search_type must be Received or Decided")
    query = urlencode({"searchType": normalised, "days": 7})
    return urljoin(source.base_url, f"Search/Standard?{query}")


def parse_south_holland_weekly_text(
    text: str,
    *,
    source: PlanningSource,
) -> list[PlanningApplication]:
    """Parse text extracted from an official South Holland validation PDF."""
    applications: list[PlanningApplication] = []
    for block in re.split(r"(?=Reference:\s*)", text or ""):
        reference_match = _REFERENCE.search(block)
        if not reference_match:
            continue
        proposal_match = re.search(
            r"Development:\s*(.*?)\s*Location:", block, re.DOTALL | re.IGNORECASE
        )
        address_match = re.search(
            r"Location:\s*(.*?)\s*Northing\s+Easting\s+Type:",
            block,
            re.DOTALL | re.IGNORECASE,
        )
        if not proposal_match or not address_match:
            continue
        dates = _DATE.findall(block)
        applications.append(
            PlanningApplication(
                reference=reference_match.group(0).upper(),
                planning_authority=source.authority_label,
                planning_source_key=source.key,
                address=_clean(address_match.group(1)),
                proposal=_clean(proposal_match.group(1)),
                status="Validated",
                received_date=dates[-2] if len(dates) >= 2 else "",
                validated_date=dates[-1] if dates else "",
                url=urljoin(source.base_url, "planningSearch"),
            )
        )
    return applications


def collect_south_holland_weekly_pdf(
    source: PlanningSource,
    *,
    session=None,
    timeout: int = 45,
) -> list[PlanningApplication]:
    """Download and parse the newest validation PDF linked by the council."""
    from bs4 import BeautifulSoup
    from pypdf import PdfReader
    import requests

    owns_session = session is None
    session = session or requests.Session()
    if hasattr(session, "headers"):
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )
    if not source.weekly_list_url:
        raise ValueError("South Holland weekly-list URL is not configured.")

    def pdf_candidates(page_html: str) -> list[str]:
        soup = BeautifulSoup(page_html, "html.parser")
        matches: list[str] = []
        for link in soup.select("a[href]"):
            href = str(link.get("href") or "").strip()
            label = _clean(link.get_text(" ", strip=True)).lower()
            href_lower = href.lower()
            is_pdf = ".pdf" in href_lower
            is_weekly_validation = (
                ("weekly" in label and "planning" in label)
                or "validation" in label
                or "weekly" in href_lower
                or "valid" in href_lower
            )
            if is_pdf and is_weekly_validation:
                matches.append(urljoin(source.weekly_list_url, href))
        return matches

    page = session.get(source.weekly_list_url, timeout=timeout)
    browser = None
    page_html = ""
    if getattr(page, "status_code", 200) != 403:
        page.raise_for_status()
        page_html = page.text
    candidates = pdf_candidates(page_html)

    # The council's anti-bot layer sometimes returns HTTP 200 with an
    # interstitial page.  Treat a link-free response exactly like a 403 and
    # let a real browser obtain the rendered weekly-list page.
    if not candidates and owns_session:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        browser = webdriver.Chrome(options=options)
        try:
            browser.get(source.weekly_list_url)
            WebDriverWait(browser, timeout).until(
                lambda driver: ".pdf" in driver.page_source.lower()
            )
            page_html = browser.page_source
            for cookie in browser.get_cookies():
                session.cookies.set(cookie["name"], cookie["value"])
            candidates = pdf_candidates(page_html)
        except Exception:
            browser.quit()
            browser = None
            raise
    if not candidates:
        if browser is not None:
            browser.quit()
        raise RuntimeError("No weekly validation PDF was found on the council page.")
    pdf_url = candidates[-1]
    try:
        response = session.get(
            pdf_url,
            timeout=timeout,
            headers={"Referer": source.weekly_list_url},
        )
        response.raise_for_status()
        reader = PdfReader(BytesIO(response.content))
        text = "\n".join(pdf_page.extract_text() or "" for pdf_page in reader.pages)
    finally:
        if browser is not None:
            browser.quit()
    applications = parse_south_holland_weekly_text(text, source=source)
    if not applications:
        raise RuntimeError("The latest South Holland weekly PDF contained no readable applications.")
    return applications


def collect_additional_source(source: PlanningSource) -> list[PlanningApplication]:
    """Dispatch an enabled non-Idox source to its isolated connector."""
    if source.platform == "south_holland_weekly_pdf":
        return collect_south_holland_weekly_pdf(source)
    if source.platform == "statmap_weekly":
        failures = []
        for weeks_back in range(5):
            list_date = date.today() - timedelta(weeks=weeks_back)
            try:
                applications = collect_west_lindsey_statmap(
                    source, weekly_date=list_date
                )
                if applications:
                    return applications
            except RuntimeError as error:
                if "contained no applications" not in str(error):
                    raise
                failures.append(str(error))
        raise RuntimeError(
            "West Lindsey had no applications in the five most recent weekly lists. "
            + " | ".join(failures)
        )
    if source.platform == "north_lincs_weekly":
        return collect_north_lincolnshire_weekly(source)
    if source.platform == "lincolnshire_county_register":
        return collect_lincolnshire_county_register(source)
    raise ValueError(f"Unsupported additional planning platform: {source.platform}")


def statmap_application_from_cells(
    cells: list[str],
    *,
    detail_url: str,
    source: PlanningSource,
) -> PlanningApplication | None:
    """Map one current StatMap weekly-list row into the shared model."""
    if len(cells) < 7:
        return None
    reference, initial_reference, address, proposal, received, status, decision = (
        _clean(value) for value in cells[:7]
    )
    if not reference or not proposal:
        return None
    return PlanningApplication(
        reference=reference,
        alt_reference=initial_reference,
        planning_authority=source.authority_label,
        planning_source_key=source.key,
        address=address,
        proposal=proposal,
        status=status,
        decision=decision,
        received_date=received,
        validated_date=received,
        url=detail_url,
    )


def collect_west_lindsey_statmap(
    source: PlanningSource,
    *,
    weekly_date: date | None = None,
) -> list[PlanningApplication]:
    """Collect every page of West Lindsey's current StatMap weekly list."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    list_date = weekly_date or date.today()
    list_date -= timedelta(days=list_date.weekday())
    base_url = source.base_url.rstrip("/")
    list_url = (
        f"{base_url}/planningapplications/"
        f"?weeklyListDate={list_date.isoformat()}"
    )
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)
    applications: list[PlanningApplication] = []
    try:
        driver.get(list_url)
        try:
            reject = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[normalize-space()='Reject additional cookies']")
                )
            )
            reject.click()
        except Exception:
            pass
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[role='grid']")))
        seen_pages: set[tuple[str, ...]] = set()
        while True:
            rows = driver.find_elements(By.CSS_SELECTOR, "[role='row']")
            page_references: list[str] = []
            for row in rows:
                cells = row.find_elements(By.CSS_SELECTOR, "[role='cell']")
                if len(cells) < 7:
                    continue
                values = [cell.text for cell in cells[:7]]
                links = cells[0].find_elements(By.TAG_NAME, "a")
                detail_url = links[0].get_attribute("href") if links else list_url
                application = statmap_application_from_cells(
                    values,
                    detail_url=detail_url,
                    source=source,
                )
                if application is not None:
                    applications.append(application)
                    page_references.append(application.reference)
            signature = tuple(page_references)
            if not signature:
                raise RuntimeError(
                    f"West Lindsey weekly list {list_date.isoformat()} contained no applications."
                )
            if signature in seen_pages:
                break
            seen_pages.add(signature)
            next_buttons = driver.find_elements(
                By.CSS_SELECTOR, "button[aria-label='next']"
            )
            if not next_buttons or not next_buttons[0].is_enabled():
                break
            previous_signature = signature
            next_buttons[0].click()
            wait.until(
                lambda active_driver: tuple(
                    cell.text
                    for cell in active_driver.find_elements(
                        By.CSS_SELECTOR,
                        "[role='row'] [role='cell']:first-child",
                    )
                )
                != previous_signature
            )
    finally:
        driver.quit()
    return applications


def application_from_label_map(
    values: dict[str, str],
    *,
    reference: str,
    detail_url: str,
    source: PlanningSource,
    default_status: str = "",
) -> PlanningApplication | None:
    """Map labelled fields used by the two remaining official registers."""
    normalised = {
        _clean(key).strip(":").lower(): _clean(value)
        for key, value in values.items()
    }

    def first(*keys: str) -> str:
        return next(
            (normalised[key] for key in keys if normalised.get(key)),
            "",
        )

    proposal = first(
        "proposal",
        "proposed development",
        "description",
        "development description",
    )
    address = first("location", "address", "site address")
    if not _clean(reference) or not proposal:
        return None
    return PlanningApplication(
        reference=_clean(reference),
        planning_authority=source.authority_label,
        planning_source_key=source.key,
        address=address,
        locality=first("town", "locality", "settlement"),
        parish=first("parish", "parishes"),
        ward=first("ward", "wards"),
        proposal=proposal,
        status=first("status") or default_status,
        decision=first("decision"),
        received_date=first("received date", "date received"),
        validated_date=first(
            "validated date", "date validated", "date valid", "registration date"
        ),
        decision_date=first("decision date", "date decided"),
        url=detail_url,
    )


def _chrome_options(*, visible: bool = False, profile_path: Path | None = None):
    from selenium.webdriver.chrome.options import Options

    options = Options()
    if not visible:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-first-run")
    if profile_path is not None:
        profile_path.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_path}")
    return options


def _label_map_from_container(container) -> dict[str, str]:
    """Extract dt/dd and table label/value pairs from a Selenium container."""
    from selenium.webdriver.common.by import By

    values: dict[str, str] = {}
    terms = container.find_elements(By.TAG_NAME, "dt")
    definitions = container.find_elements(By.TAG_NAME, "dd")
    for term, definition in zip(terms, definitions):
        values[_clean(term.text)] = _clean(definition.text)
    for row in container.find_elements(By.CSS_SELECTOR, "tr"):
        cells = row.find_elements(By.CSS_SELECTOR, "th, td")
        if len(cells) >= 2:
            values[_clean(cells[0].text)] = _clean(cells[1].text)
    keys = container.find_elements(
        By.CSS_SELECTOR,
        ".govuk-summary-list__key, .summary-list__key, [class*='label']",
    )
    for key in keys:
        key_text = _clean(key.text)
        if not key_text:
            continue
        try:
            value = key.find_element(
                By.XPATH,
                "following-sibling::*[1]",
            )
        except Exception:
            continue
        value_text = _clean(value.text)
        if value_text:
            values.setdefault(key_text, value_text)
    return values


def collect_lincolnshire_county_register(
    source: PlanningSource,
) -> list[PlanningApplication]:
    """Collect registered and determined county applications from the last week."""
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    applications: list[PlanningApplication] = []
    searches = (
        ("Received", "Validated"),
        ("Decided", "Decided"),
    )
    for search_type, default_status in searches:
        search_name = search_type.lower()
        last_error = None
        for attempt in range(3):
            last_error = None
            driver = webdriver.Chrome(options=_chrome_options())
            wait = WebDriverWait(driver, 45)
            search_applications: list[PlanningApplication] = []
            try:
                driver.get(source.base_url)
                disclaimer_buttons = driver.find_elements(
                    By.CSS_SELECTOR, "input[type='submit'][value='Agree']"
                )
                if disclaimer_buttons:
                    disclaimer_buttons[0].click()
                    wait.until(lambda active: "/Disclaimer" not in active.current_url)
                # The landing page sometimes finishes its redirect before its
                # convenience links are present.  The register exposes stable
                # official routes for these rolling searches, so use them
                # directly rather than treating a missing landing-page link as
                # a failed source.
                target_url = lincolnshire_county_seven_day_url(
                    source,
                    search_type=search_type,
                )
                driver.get(target_url)
                wait.until(
                    lambda active: "/Search/Results" in active.current_url
                    or "/Planning/Display" in active.current_url
                    or "no results found" in active.page_source.lower()
                )
                if "no results found" in driver.page_source.lower():
                    search_applications = []
                elif "/Planning/Display" in driver.current_url:
                    # DEF's register automatically opens the application when
                    # a search has exactly one result.  Treat that detail page
                    # as a valid one-item result rather than waiting forever
                    # for a results list that the portal has skipped.
                    wait.until(
                        lambda active: active.find_elements(By.TAG_NAME, "body")
                        and _label_map_from_container(
                            active.find_element(By.TAG_NAME, "body")
                        )
                    )
                    query = parse_qs(urlparse(driver.current_url).query)
                    reference = _clean(
                        (query.get("applicationNumber") or [""])[0]
                    )
                    application = application_from_label_map(
                        _label_map_from_container(
                            driver.find_element(By.TAG_NAME, "body")
                        ),
                        reference=reference,
                        detail_url=driver.current_url,
                        source=source,
                        default_status=default_status,
                    )
                    if application is None:
                        raise RuntimeError(
                            "single-result detail page contained no readable application"
                        )
                    search_applications = [application]
                else:
                    page_number = 1
                    while True:
                        wait.until(
                            lambda active: active.find_elements(
                                By.CSS_SELECTOR, "dl.dl-horizontal"
                            )
                        )
                        containers = driver.find_elements(
                            By.CSS_SELECTOR, "dl.dl-horizontal"
                        )
                        for container in containers:
                            detail_links = container.find_elements(
                                By.CSS_SELECTOR, "a[href*='/Planning/Display']"
                            )
                            if not detail_links:
                                continue
                            reference = _clean(detail_links[0].text)
                            application = application_from_label_map(
                                _label_map_from_container(container),
                                reference=reference,
                                detail_url=detail_links[0].get_attribute("href"),
                                source=source,
                                default_status=default_status,
                            )
                            if application is not None:
                                search_applications.append(application)
                        next_page = page_number + 1
                        next_links = driver.find_elements(
                            By.CSS_SELECTOR,
                            f"a[href='/Search/Results/{next_page}']",
                        )
                        if not next_links:
                            break
                        next_url = next_links[0].get_attribute("href")
                        driver.get(next_url)
                        page_number = next_page
                        wait.until(
                            lambda active: f"Page {page_number} of"
                            in active.page_source
                        )
            except Exception as error:
                last_error = error
            finally:
                driver.quit()
            if last_error is None:
                applications.extend(search_applications)
                break
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
        else:
            message = _clean(str(last_error)) or (
                f"{type(last_error).__name__}: browser timed out or returned an unusable page"
            )
            raise RuntimeError(
                f"Lincolnshire County Council {search_name} seven-day search "
                f"failed after three attempts: {message}"
            ) from last_error
    return applications


def collect_north_lincolnshire_weekly(
    source: PlanningSource,
) -> list[PlanningApplication]:
    """Collect North Lincolnshire's official received and decided weekly lists."""
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    profile_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "north_lincolnshire_browser_profile"
    )
    driver = webdriver.Chrome(
        options=_chrome_options(visible=True, profile_path=profile_path)
    )
    wait = WebDriverWait(driver, 300)
    applications: list[PlanningApplication] = []
    reference_pattern = re.compile(r"\bPA/\d{4}/\d+\b", re.IGNORECASE)
    try:
        for control_text, default_status in (
            ("New this week", "Validated"),
            ("Decided this week", "Decided"),
        ):
            control_applications = None
            last_error = None
            for control_attempt in range(3):
                try:
                    driver.get(source.base_url)
                    wait.until(
                        lambda active: "verifying that you are not a robot"
                        not in active.page_source.lower()
                    )
                    cookie_buttons = driver.find_elements(
                        By.XPATH,
                        "//button[normalize-space()='Only essentials']",
                    )
                    if cookie_buttons:
                        try:
                            driver.execute_script(
                                "arguments[0].click();", cookie_buttons[0]
                            )
                            time.sleep(1)
                        except Exception:
                            pass
                    controls = wait.until(
                        lambda active: active.find_elements(
                            By.XPATH,
                            f"//button[normalize-space()='{control_text}']"
                            f" | //a[normalize-space()='{control_text}']",
                        )
                    )
                    driver.execute_script("arguments[0].click();", controls[0])
                    wait.until(
                        lambda active: active.find_elements(
                            By.CSS_SELECTOR, "a[href*='/application/']"
                        )
                        or "no results found" in active.page_source.lower()
                        or "no applications" in active.page_source.lower()
                    )
                    raw_links = driver.execute_script(
                        "return Array.from(document.querySelectorAll('a[href]'))"
                        ".map(a => [a.innerText || a.textContent || '', a.href]);"
                    )
                    detail_links: list[tuple[str, str]] = []
                    seen_urls: set[str] = set()
                    for text_value, href in raw_links:
                        reference_match = reference_pattern.search(_clean(text_value))
                        if reference_match and href and href not in seen_urls:
                            seen_urls.add(href)
                            detail_links.append(
                                (reference_match.group(0).upper(), href)
                            )
                    if not detail_links:
                        page_text = driver.page_source.lower()
                        if "no applications" in page_text or "no results" in page_text:
                            control_applications = []
                            break
                        raise RuntimeError(
                            f"North Lincolnshire '{control_text}' list contained no application links."
                        )
                    downloaded = []
                    for reference, detail_url in detail_links:
                        application = None
                        for detail_attempt in range(3):
                            try:
                                driver.get(detail_url)
                                wait.until(
                                    lambda active: reference.lower()
                                    in active.page_source.lower()
                                )
                                body = driver.find_element(By.TAG_NAME, "body")
                                application = application_from_label_map(
                                    _label_map_from_container(body),
                                    reference=reference,
                                    detail_url=detail_url,
                                    source=source,
                                    default_status=default_status,
                                )
                                break
                            except StaleElementReferenceException:
                                if detail_attempt == 2:
                                    raise
                                time.sleep(1)
                        if application is not None:
                            downloaded.append(application)
                    control_applications = downloaded
                    break
                except StaleElementReferenceException as error:
                    last_error = error
                    if control_attempt < 2:
                        time.sleep(2)
                        continue
                    raise RuntimeError(
                        f"North Lincolnshire '{control_text}' page changed repeatedly "
                        "while it was being read."
                    ) from error
                except Exception as error:
                    last_error = error
                    if "verifying that you are not a robot" in driver.page_source.lower():
                        raise RuntimeError(
                            "North Lincolnshire portal browser verification did not clear."
                        ) from error
                    if control_attempt < 2:
                        time.sleep(2)
                        continue
                    raise
            if control_applications is None:
                raise RuntimeError(
                    f"North Lincolnshire '{control_text}' collection failed: "
                    f"{_clean(str(last_error)) or type(last_error).__name__}"
                )
            applications.extend(control_applications)
    finally:
        driver.quit()
    return applications
