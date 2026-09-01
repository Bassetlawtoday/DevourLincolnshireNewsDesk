from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import time

from services.models import PlanningApplication


WEEKLY_URL = (
    "https://publicaccess.bassetlaw.gov.uk/"
    "online-applications/search.do?"
    "action=weeklyList&searchType=Application"
)


RESULTS_URL = (
    "https://publicaccess.bassetlaw.gov.uk/"
    "online-applications/weeklyListResults.do?"
    "action=firstPage"
)


class PlanningScraper:

    def __init__(self):

        options = Options()

        # Planning collection runs in the background; the browser remains
        # available to Selenium without opening a visible Chrome window.
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=options)

        self.wait = WebDriverWait(self.driver, 20)

        self.applications = []

    ####################################################################
    # Browser
    ####################################################################

    def close(self):

        try:
            self.driver.quit()

        except:

            pass

    ####################################################################
    # Weekly List
    ####################################################################

    def open_weekly_list(self, list_type="decided", wait_for_user=True):

        list_type = list_type.strip().lower()

        if list_type not in {"decided", "validated"}:
            raise ValueError(
                "list_type must be either 'decided' or 'validated'"
            )

        radio_id = (
            "dateDecided"
            if list_type == "decided"
            else "dateValidated"
        )

        self.driver.get(WEEKLY_URL)

        self.wait.until(
            EC.presence_of_element_located((By.ID, "week"))
        )

        if wait_for_user:
            print()
            print("=" * 60)
            print("Waiting for Weekly List page...")
            print("=" * 60)
            print("Waiting for the planning portal to finish loading...")

        self.wait.until(
            EC.element_to_be_clickable((By.ID, radio_id))
        )

        if wait_for_user:
            print("Portal ready.")

        week_selector = Select(
            self.driver.find_element(By.ID, "week")
        )

        weeks = []

        for index, option in enumerate(week_selector.options):
            label = option.text.strip()
            value = (option.get_attribute("value") or "").strip()

            if not label:
                continue

            if not value and "select" in label.lower():
                continue

            weeks.append((index, value, label))

        if not weeks:
            raise RuntimeError(
                "The planning portal did not provide any weekly-list dates."
            )

        print()
        print(
            f"Checking {len(weeks)} available weeks for "
            f"{list_type} applications..."
        )

        no_results_phrases = (
            "no results found",
            "please check the search criteria",
            "your search returned no results",
        )

        for position, (_, week_value, week_label) in enumerate(
            weeks,
            start=1,
        ):

            print()
            print(
                f"Checking {list_type} applications for "
                f"{week_label} ({position}/{len(weeks)})..."
            )

            self.driver.get(WEEKLY_URL)

            self.wait.until(
                EC.presence_of_element_located((By.ID, "week"))
            )

            self.wait.until(
                EC.element_to_be_clickable((By.ID, radio_id))
            ).click()

            current_selector = Select(
                self.driver.find_element(By.ID, "week")
            )

            selected = False

            if week_value:
                try:
                    current_selector.select_by_value(week_value)
                    selected = True
                except Exception:
                    pass

            if not selected:
                try:
                    current_selector.select_by_visible_text(week_label)
                    selected = True
                except Exception:
                    pass

            if not selected:
                print(
                    f"Could not select week {week_label}; "
                    "trying the previous available week."
                )
                continue

            old_url = self.driver.current_url
            old_source = self.driver.page_source

            self.driver.find_element(
                By.XPATH,
                "//input[@value='Search']"
            ).click()

            try:
                WebDriverWait(self.driver, 20).until(
                    lambda driver: (
                        driver.current_url != old_url
                        or driver.page_source != old_source
                        or len(driver.find_elements(By.ID, "resultsPerPage")) > 0
                    )
                )
            except TimeoutException:
                pass

            page_text = self.driver.page_source.lower()

            if self.driver.find_elements(By.ID, "resultsPerPage"):
                print()
                print(
                    f"Weekly {list_type.title()} Results page loaded "
                    f"for {week_label}."
                )
                return

            if any(phrase in page_text for phrase in no_results_phrases):
                print(
                    f"No {list_type} applications found for "
                    f"{week_label}."
                )

                if position < len(weeks):
                    print("Trying the previous available week...")

                continue

            print(
                f"The portal did not return a usable results page for "
                f"{week_label}."
            )

            if position < len(weeks):
                print("Trying the previous available week...")

        raise RuntimeError(
            f"No {list_type} applications were found in any available week."
        )

    ####################################################################
    # Results Per Page
    ####################################################################

    def set_results_per_page(self):

        print()

        print("Changing results per page to 100...")

        selector = Select(

            self.driver.find_element(

                By.ID,

                "resultsPerPage"

            )

        )

        old_source = self.driver.page_source
        selector.select_by_value("100")

        try:
            self.wait.until(
                lambda driver: (
                    Select(driver.find_element(By.ID, "resultsPerPage"))
                    .first_selected_option
                    .get_attribute("value") == "100"
                    and driver.page_source != old_source
                )
            )
        except TimeoutException:
            self.wait.until(
                lambda driver: (
                    Select(driver.find_element(By.ID, "resultsPerPage"))
                    .first_selected_option
                    .get_attribute("value") == "100"
                )
            )

        print("Done.")

    ####################################################################
# Find all applications
####################################################################

    def get_application_links(self):

        print()
        print("Collecting applications...")

        application_links = []
        seen_application_links = set()
        visited_pages = set()
        page_number = 1

        while True:

            self.wait.until(
                lambda driver: driver.execute_script(
                    "return document.readyState"
                ) == "complete"
            )

            current_url = self.driver.current_url
            page_source = self.driver.page_source
            page_signature = (current_url, hash(page_source))

            if page_signature in visited_pages:
                break

            visited_pages.add(page_signature)

            page_soup = BeautifulSoup(page_source, "html.parser")
            page_new_links = 0

            for anchor in page_soup.find_all("a", href=True):

                href = anchor.get("href", "").strip()

                if not href:
                    continue

                absolute_url = urljoin(current_url, href)
                parsed = urlparse(absolute_url)
                query = parse_qs(parsed.query)

                is_application_link = (
                    "applicationDetails.do" in parsed.path
                    or "keyVal" in query
                )

                if not is_application_link or "keyVal" not in query:
                    continue

                query["activeTab"] = ["summary"]
                normalised_query = urlencode(query, doseq=True)
                normalised_url = urlunparse(
                    parsed._replace(query=normalised_query)
                )

                if normalised_url in seen_application_links:
                    continue

                seen_application_links.add(normalised_url)
                application_links.append(normalised_url)
                page_new_links += 1

            print(
                f"Results page {page_number}: "
                f"{page_new_links} new application links found."
            )

            next_link = None

            next_selectors = [
                "a[rel='next']",
                "a.next",
                "li.next a",
                "a[href*='action=nextPage']",
                "a[href*='page=next']",
            ]

            for selector in next_selectors:
                candidate = page_soup.select_one(selector)

                if candidate and candidate.get("href"):
                    next_link = candidate
                    break

            if next_link is None:
                for anchor in page_soup.find_all("a", href=True):
                    label = anchor.get_text(" ", strip=True).lower()
                    title = anchor.get("title", "").strip().lower()

                    if label in {"next", "next >", ">", "›", "»"}:
                        next_link = anchor
                        break

                    if "next" in title:
                        next_link = anchor
                        break

            if next_link is None:
                break

            classes = {str(item).lower() for item in next_link.get("class", [])}
            parent_classes = {
                str(item).lower()
                for item in (
                    next_link.parent.get("class", [])
                    if next_link.parent else []
                )
            }

            if "disabled" in classes or "disabled" in parent_classes:
                break

            next_href = next_link.get("href", "").strip()

            if not next_href or next_href.lower().startswith("javascript:"):
                break

            next_url = urljoin(current_url, next_href)

            if next_url == current_url:
                break

            previous_source = page_source
            self.driver.get(next_url)

            try:
                self.wait.until(
                    lambda driver: driver.page_source != previous_source
                )
            except Exception:
                break

            page_number += 1

        print()
        print(f"{len(application_links)} applications discovered.")

        return application_links


    ####################################################################
    # Download everything
    ####################################################################

    def scrape(self):

        self.open_weekly_list()

        self.set_results_per_page()

        links = self.get_application_links()

        total = len(links)

        counter = 1

        for link in links:

            print()

            print(f"{counter} / {total}")

            app = self.scrape_application(link)

            if app:

                self.applications.append(app)

            counter += 1

        return self.applications
    ####################################################################
    # Individual Application
    ####################################################################

    def scrape_application(self, url):

        max_attempts = 3

        for attempt in range(1, max_attempts + 1):

            try:

                # Small human-like pause between requests
                time.sleep(1.5)

                self.driver.get(url)

                self.wait.until(
                    EC.presence_of_element_located(
                        (By.ID, "simpleDetailsTable")
                    )
                )

                time.sleep(0.5)
                break

            except (TimeoutException, WebDriverException):

                page = self.driver.page_source.lower()

                if "429" in page or "too many requests" in page:
                    wait_time = 30 * attempt
                    print(f"429 rate limit detected. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    print(
                        f"Application page failed to load "
                        f"(attempt {attempt}/{max_attempts}): {url}"
                    )
                    time.sleep(3 * attempt)

                if attempt == max_attempts:
                    print(f"Skipping application after {max_attempts} attempts: {url}")
                    return None

        soup = BeautifulSoup(

            self.driver.page_source,

            "html.parser"

        )

        application = PlanningApplication()
        application.url = str(url or "").strip()

        ################################################################
        # Header information
        ################################################################

        crumb = soup.find("div", class_="addressCrumb")

        if crumb:

            ref = crumb.find("span", class_="caseNumber")

            if ref:

                application.reference = ref.get_text(strip=True)

            proposal = crumb.find("span", class_="description")

            if proposal:

                application.proposal = proposal.get_text(
                    " ",
                    strip=True
                )

            address = crumb.find("span", class_="address")

            if address:

                application.address = address.get_text(
                    " ",
                    strip=True
                )

            decision = crumb.find(
                "span",
                class_="badge-decided"
            )

            if decision:

                application.decision = decision.get_text(
                    " ",
                    strip=True
                )

        ################################################################
        # Summary Table
        ################################################################

        table = soup.find(

            "table",

            id="simpleDetailsTable"

        )

        if table:

            rows = table.find_all("tr")

            for row in rows:

                th = row.find("th")

                td = row.find("td")

                if not th or not td:

                    continue

                field = th.get_text(
                    " ",
                    strip=True
                )

                value = td.get_text(
                    " ",
                    strip=True
                )

                self.assign_field(
                    application,
                    field,
                    value
                )

        ################################################################
        # Count comments
        ################################################################

        comments_tab = soup.find(

            "a",

            id="tab_makeComment"

        )

        if comments_tab:

            text = comments_tab.get_text(
                " ",
                strip=True
            )

            digits = ""

            for c in text:

                if c.isdigit():

                    digits += c

            if digits:

                application.notes += (
                    f"Comments:{digits}; "
                )

        ################################################################
        # Count documents
        ################################################################

        documents_tab = soup.find(

            "a",

            id="tab_documents"

        )

        if documents_tab:

            text = documents_tab.get_text(
                " ",
                strip=True
            )

            digits = ""

            for c in text:

                if c.isdigit():

                    digits += c

            if digits:

                application.notes += (
                    f"Documents:{digits}; "
                )

        ################################################################
        # Score
        ################################################################

        application.score = self.score_application(
            application
        )

        application.category = self.detect_category(
            application
        )

        return application
    ####################################################################
    # Assign fields
    ####################################################################

    def assign_field(self, application, field, value):

        field = field.lower().strip()

        if field == "reference":
            application.reference = value

        elif field == "alternative reference":
            application.alt_reference = value

        elif field == "application received":
            application.received_date = value

        elif field == "application validated":
            application.validated_date = value

        elif field == "address":
            application.address = value

        elif field == "proposal":
            application.proposal = value

        elif field == "status":
            application.status = value

        elif field == "decision":
            application.decision = value

        elif field == "decision issued date":
            application.decision_date = value

        elif field == "appeal status":
            application.appeal_status = value

        elif field == "appeal decision":
            application.appeal_decision = value

    ####################################################################
    # Detect Category
    ####################################################################

    def detect_category(self, application):

        text = (
            application.proposal + " " +
            application.address
        ).lower()

        if "tree" in text:
            return "Trees"

        if "dwelling" in text:
            return "Housing"

        if "house" in text:
            return "Housing"

        if "extension" in text:
            return "Extension"

        if "solar" in text:
            return "Solar Farm"

        if "battery" in text:
            return "Battery Storage"

        if "telecommunication" in text:
            return "Telecommunications"

        if "mast" in text:
            return "Telecommunications"

        if "agricultural" in text:
            return "Agriculture"

        if "listed building" in text:
            return "Listed Building"

        if "conservation" in text:
            return "Conservation"

        if "change of use" in text:
            return "Change of Use"

        if "industrial" in text:
            return "Industrial"

        if "warehouse" in text:
            return "Industrial"

        if "school" in text:
            return "Education"

        if "care home" in text:
            return "Care"

        if "pub" in text:
            return "Hospitality"

        if "restaurant" in text:
            return "Hospitality"

        if "shop" in text:
            return "Retail"

        return "General"

    ####################################################################
    # Newsworthiness Score
    ####################################################################

    def score_application(self, application):

        score = 0

        proposal = application.proposal.lower()

        address = application.address.lower()

        if "solar" in proposal:
            score += 50

        if "battery" in proposal:
            score += 50

        if "100 dwellings" in proposal:
            score += 100

        if "50 dwellings" in proposal:
            score += 75

        if "dwelling" in proposal:
            score += 35

        if "care home" in proposal:
            score += 40

        if "school" in proposal:
            score += 40

        if "supermarket" in proposal:
            score += 50

        if "industrial" in proposal:
            score += 35

        if "warehouse" in proposal:
            score += 30

        if "listed building" in proposal:
            score += 35

        if "demolition" in proposal:
            score += 40

        if "tree" in proposal:
            score += 5

        if "retford" in address:
            score += 10

        if "worksop" in address:
            score += 10

        if "harworth" in address:
            score += 10

        if "tuxford" in address:
            score += 10

        if "blyth" in address:
            score += 10

        if "misterton" in address:
            score += 10

        if "babworth" in address:
            score += 8

        if score > 100:
            score = 100

        return score
     ####################################################################
    # Remove duplicates
    ####################################################################

    def remove_duplicates(self):

        unique = {}

        for app in self.applications:

            if not app.reference:
                continue

            unique[app.reference] = app

        self.applications = list(unique.values())

    ####################################################################
    # Sort by score
    ####################################################################

    def sort_by_score(self):

        self.applications.sort(

            key=lambda x: x.score,

            reverse=True

        )

    ####################################################################
    # Return highest scoring
    ####################################################################

    def top_stories(self, minimum_score=20):

        stories = []

        for app in self.applications:

            if app.score >= minimum_score:

                stories.append(app)

        return stories

    ####################################################################
    # Display
    ####################################################################

    def print_summary(self):

        print()

        print("=" * 70)

        print("PLANNING SUMMARY")

        print("=" * 70)

        for app in self.applications:

            print()

            print(app.reference)

            print(app.address)

            print(app.category)

            print(app.score)

            print(app.decision)

    ####################################################################
    # Database hook
    ####################################################################

    def save_to_database(self):

        try:

            from database.database import save_planning_application

        except Exception:

            print("Database module not available.")

            return

        total = 0

        for app in self.applications:

            try:

                save_planning_application(app)

                total += 1

            except Exception as e:

                print(e)

        print()

        print(f"{total} applications saved.")

####################################################################
# Public entry point
####################################################################

def run_scraper():

    scraper = PlanningScraper()

    try:

        applications = scraper.scrape()

        scraper.remove_duplicates()

        scraper.sort_by_score()

        scraper.save_to_database()

        scraper.print_summary()

        return scraper.applications

    finally:

        scraper.close()


if __name__ == "__main__":

    apps = run_scraper()

    print()

    print(f"Downloaded {len(apps)} planning applications.")
