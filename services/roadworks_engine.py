from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from services.roadworks_models import RoadworkRecord
from services.roadworks_scraper import RoadworksScraper


NEWSWORTHY_SCORE = 40
FRONT_PAGE_SCORE = 80
LEAD_WEBSITE_SCORE = 60
WEBSITE_STORY_SCORE = 40

TOP_STORY_LIMIT = 10
WATCHLIST_LIMIT = 12
WATCHLIST_MINIMUM_SCORE = 20


def run_weekly_download(ui) -> int:
    """
    Run the Roadworks and Travel Intelligence download.

    This is the public entry point used by modules/roadworks.py.
    """

    scraper = RoadworksScraper()

    try:
        ui.set_status("Connecting to roadworks and travel sources")
        ui.set_current_application("Preparing roadworks download")
        ui.set_progress(0.10, "Starting")
        ui.write_log("Roadworks engine started.")

        ui.set_progress(0.30, "Connecting")
        ui.write_log("Connecting to roadworks and travel sources...")

        downloaded_records = scraper.scrape()

        ui.set_progress(0.55, "Validating Records")
        ui.set_current_application("Validating downloaded records")

        records = normalise_records(downloaded_records, ui)

        ui.set_list_progress(
            "Roadworks records",
            len(records),
            len(records),
        )

        ui.set_progress(0.70, "Processing Records")
        ui.set_current_application("Building editorial intelligence")
        ui.write_log(f"{len(records)} roadworks records collected.")

        report_data = build_report_data(records)
        ui.set_report_data(report_data)

        ui.set_progress(0.90, "Preparing Briefing")
        ui.set_current_application("Preparing editor's briefing")

        ui.write_log(
            f"{report_data['road_closures']} road closures identified."
        )
        ui.write_log(
            f"{report_data['newsworthy_stories']} potential stories identified."
        )

        ui.set_progress(1.00, "Complete")
        ui.set_status("Complete")
        ui.set_current_application("Finished")
        ui.write_log("Roadworks download completed.")

        return len(records)

    finally:
        scraper.close()


def normalise_records(
    downloaded_records: Iterable[RoadworkRecord] | None,
    ui=None,
) -> list[RoadworkRecord]:
    """
    Validate and remove duplicate RoadworkRecord objects.

    Invalid objects, records with unusable unique keys and duplicates are
    skipped so that one faulty source record does not prevent the complete
    Roadworks module from running.
    """

    if downloaded_records is None:
        return []

    unique_records: list[RoadworkRecord] = []
    seen_keys: set[Any] = set()

    invalid_count = 0
    duplicate_count = 0
    key_error_count = 0

    for record in downloaded_records:
        if not isinstance(record, RoadworkRecord):
            invalid_count += 1
            continue

        try:
            key = record.unique_key()
            hash(key)
        except (AttributeError, TypeError, ValueError):
            key_error_count += 1
            continue

        if key in seen_keys:
            duplicate_count += 1
            continue

        seen_keys.add(key)
        unique_records.append(record)

    if ui is not None:
        if invalid_count:
            ui.write_log(
                f"Skipped {invalid_count} invalid roadworks record(s)."
            )

        if key_error_count:
            ui.write_log(
                f"Skipped {key_error_count} roadworks record(s) "
                "with invalid unique keys."
            )

        if duplicate_count:
            ui.write_log(
                f"Removed {duplicate_count} duplicate roadworks record(s)."
            )

    return unique_records


def build_report_data(
    records: list[RoadworkRecord],
) -> dict:
    """
    Convert RoadworkRecord objects into data used by the report window.
    """

    sorted_records = sorted(
        records,
        key=_record_sort_key,
    )

    record_dicts = [
        record.to_dict()
        for record in sorted_records
    ]

    newsworthy_records = [
        record
        for record in sorted_records
        if _record_score(record) >= NEWSWORTHY_SCORE
    ]

    road_closures = sum(
        1
        for record in records
        if record.is_road_closed
    )

    emergency_works = sum(
        1
        for record in records
        if record.is_emergency
    )

    overnight_works = sum(
        1
        for record in records
        if record.is_overnight
    )

    category_breakdown = build_category_breakdown(records)
    area_breakdown = build_area_breakdown(records)

    top_stories = [
        record.to_dict()
        for record in newsworthy_records[:TOP_STORY_LIMIT]
    ]

    watchlist = build_watchlist(sorted_records)
    editorial_summary = build_editorial_summary(records)

    return {
        # Current Roadworks report fields
        "total_records": len(records),
        "newsworthy_stories": len(newsworthy_records),
        "front_page_candidates": editorial_summary["front_page"],
        "road_closures": road_closures,
        "emergency_works": emergency_works,
        "overnight_works": overnight_works,
        "top_stories": top_stories,
        "all_records": record_dicts,
        "category_breakdown": category_breakdown,
        "area_breakdown": area_breakdown,
        "watchlist": watchlist,
        "editorial_summary": editorial_summary,

        # Temporary compatibility fields
        "applications_processed": len(records),
        "all_applications": record_dicts,
    }


def build_category_breakdown(
    records: list[RoadworkRecord],
) -> dict:
    """
    Count records by disruption category.
    """

    categories: Counter[str] = Counter()

    for record in records:
        category = clean_label(record.category, "Roadworks")
        categories[category] += 1

    return sort_counter(categories)


def build_area_breakdown(
    records: list[RoadworkRecord],
) -> dict:
    """
    Count records by town or location.
    """

    areas: Counter[str] = Counter()

    for record in records:
        area = (
            clean_label(record.town)
            or clean_label(record.location)
            or "Area not specified"
        )

        areas[area] += 1

    return sort_counter(areas)


def build_watchlist(
    records: list[RoadworkRecord],
) -> list[dict]:
    """
    Select records worth monitoring that are not already top stories.

    Emergency works, closures and medium-scoring records are retained for
    editorial review.
    """

    watchlist: list[dict] = []

    for record in records:
        score = _record_score(record)

        should_watch = (
            record.is_emergency
            or record.is_road_closed
            or score >= WATCHLIST_MINIMUM_SCORE
        )

        if not should_watch:
            continue

        if score >= NEWSWORTHY_SCORE:
            continue

        watchlist.append(record.to_dict())

        if len(watchlist) >= WATCHLIST_LIMIT:
            break

    return watchlist


def build_editorial_summary(
    records: list[RoadworkRecord],
) -> dict:
    """
    Group records into editorial priority bands.
    """

    summary = {
        "front_page": 0,
        "lead_website": 0,
        "website_story": 0,
        "brief_mention": 0,
    }

    for record in records:
        score = _record_score(record)

        if score >= FRONT_PAGE_SCORE:
            summary["front_page"] += 1

        elif score >= LEAD_WEBSITE_SCORE:
            summary["lead_website"] += 1

        elif score >= WEBSITE_STORY_SCORE:
            summary["website_story"] += 1

        else:
            summary["brief_mention"] += 1

    return summary


def sort_counter(counter: Counter) -> dict:
    """
    Return a Counter as a consistently ordered dictionary.

    Highest totals are shown first, with alphabetical ordering used when
    totals are equal.
    """

    ordered_items = sorted(
        counter.items(),
        key=lambda item: (-item[1], str(item[0]).lower()),
    )

    return dict(ordered_items)


def clean_label(
    value,
    fallback: str = "",
) -> str:
    """
    Return a clean display label.
    """

    if value is None:
        return fallback

    text = str(value).strip()

    return text or fallback


def _record_score(record: RoadworkRecord) -> float:
    """
    Return a numeric score without allowing malformed values to stop a report.
    """

    try:
        return float(record.score)
    except (TypeError, ValueError):
        return 0.0


def _record_sort_key(record: RoadworkRecord) -> tuple:
    """
    Sort records by score and then by stable display fields.

    The additional fields make report ordering deterministic where scores are
    equal.
    """

    return (
        -_record_score(record),
        clean_label(record.town).lower(),
        clean_label(record.location).lower(),
        clean_label(record.category).lower(),
    )