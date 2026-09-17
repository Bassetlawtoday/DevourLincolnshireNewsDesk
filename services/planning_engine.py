import re
import time
from collections import Counter
from datetime import datetime, timezone

from editorial.editorial_engine import analyse_application
from editorial.priority_engine import score_story
from editorial.scoring import (    
    editorial_summary,
)


from services.planning_scraper import PlanningScraper
from services.planning_additional_sources import collect_additional_source
from services.planning_sources import enabled_additional_sources, enabled_idox_sources
from services.planning_source_cache import PlanningSourceCache
from services.planning_reporting import (
    area_breakdown as _area_breakdown,
    authority_breakdown as _authority_breakdown,
    resolved_area as _resolved_area,
    unavailable_area_count as _unavailable_area_count,
)

from database.database import (
    total_applications,
    get_newsworthy,
)


TOP_STORY_LIMIT = 5


def _clean_text(value):
    return " ".join(str(value or "").split())


def _normalise_category(value):
    category = _clean_text(value)
    return category if category else "Uncategorised"


def _error_text(error):
    message = _clean_text(str(error))
    return message or f"{type(error).__name__}: no diagnostic message was returned"



def _proposal_summary(proposal, maximum_length=300):
    text = _clean_text(proposal) or "Proposal details unavailable"

    if len(text) <= maximum_length:
        return text

    shortened = text[: maximum_length - 3].rsplit(" ", 1)[0]
    return f"{shortened}..."


def _contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def _numbers_in_text(text):
    return [int(value) for value in re.findall(r"\b\d{1,4}\b", text)]









def _hotspot_insight(area_breakdown):
    """Add a simple editorial status to each planning hotspot."""
    if not area_breakdown:
        return []

    maximum = max(int(item.get("count", 0)) for item in area_breakdown) or 1
    enriched = []

    for position, item in enumerate(area_breakdown, start=1):
        count = int(item.get("count", 0))

        if position == 1 and count >= 3:
            status = "Leading hotspot"
        elif count >= max(2, round(maximum * 0.6)):
            status = "High activity"
        elif count >= 2:
            status = "Worth watching"
        else:
            status = "Routine activity"

        enriched.append(
            {
                "name": item.get("name", "Unknown"),
                "count": count,
                "status": status,
            }
        )

    return enriched


def _priority_for_application(app):
    """Score one application with the shared Editorial Intelligence Core."""
    title = _clean_text(app.proposal) or "Planning application"
    summary_parts = (
        _clean_text(app.address),
        _normalise_category(app.category),
        _clean_text(app.status),
        _clean_text(app.decision),
    )
    summary = " | ".join(part for part in summary_parts if part)

    text = f"{title} {summary}".lower()
    extra_signals = []

    if _is_major_housing(app):
        numbers = [value for value in _numbers_in_text(text) if value >= 10]
        extra_signals.append(
            "very large housing" if any(value >= 100 for value in numbers)
            else "major housing"
        )

    signal_groups = (
        ("battery storage", ("battery", "energy storage", "bess")),
        ("solar farm", ("solar farm",)),
        ("solar", ("solar", "photovoltaic")),
        ("renewable", ("renewable", "wind turbine")),
        ("listed building", ("listed building",)),
        ("heritage", ("heritage",)),
        ("conservation area", ("conservation area",)),
        ("employment site", ("employment site",)),
        ("employment", ("employment",)),
        ("industrial", ("industrial",)),
        ("warehouse", ("warehouse",)),
        ("retail", ("retail",)),
        ("telecommunications", ("telecommunications",)),
        ("telecom", ("telecom",)),
        ("mast", ("mast", "antenna")),
        ("5g", ("5g",)),
        ("school", ("school",)),
        ("care home", ("care home",)),
        ("hotel", ("hotel",)),
        ("demolition", ("demolition",)),
    )

    for signal, phrases in signal_groups:
        if _contains_any(text, phrases):
            extra_signals.append(signal)

    result = score_story(
        module="planning",
        title=title,
        summary=summary,
        extra_signals=extra_signals,
    )

    # Preserve compatibility with the scraper, database and existing UI,
    # all of which already understand app.score.
    app.score = int(result.score)
    return result


def _is_newsworthy(priority):
    """Use the central star rating instead of a local score threshold."""
    return int(priority.rating) >= 3


def _is_front_page(priority):
    """Front-page status is controlled by the central priority engine."""
    return int(priority.rating) >= 5


def _application_to_dict(app):
    priority = _priority_for_application(app)
    analysis = analyse_application(app)

    return {
        **analysis,
        "reference": _clean_text(app.reference),
        "planning_authority": _clean_text(
            getattr(app, "planning_authority", "")
        ),
        "planning_source_key": _clean_text(
            getattr(app, "planning_source_key", "")
        ),
        "address": _clean_text(app.address),
        "locality": _clean_text(getattr(app, "locality", "")),
        "parish": _clean_text(getattr(app, "parish", "")),
        "ward": _clean_text(getattr(app, "ward", "")),
        "area": _resolved_area(app, priority.matched_place),
        "proposal": _clean_text(app.proposal),
        "proposal_summary": _proposal_summary(app.proposal),
        "status": _clean_text(app.status),
        "decision": _clean_text(app.decision),
        "received_date": _clean_text(app.received_date),
        "validated_date": _clean_text(app.validated_date),
        "decision_date": _clean_text(app.decision_date),
        "category": _normalise_category(app.category),
        "url": _clean_text(getattr(app, "url", "")),
        "score": int(priority.score),
        "rating": int(priority.rating),
        "stars": int(priority.rating),
        "priority_level": priority.level,
        "editorial_zone_key": priority.zone_key,
        "editorial_zone": priority.zone_label,
        "matched_place": priority.matched_place,
        "priority_reasons": list(priority.reasons),
        "matched_signals": list(priority.matched_signals),
    }



def _category_breakdown(applications):
    counts = Counter(
        _normalise_category(app.category)
        for app in applications
    )
    return [
        {"name": name, "count": count}
        for name, count in counts.most_common()
    ]


def _is_major_housing(app):
    text = f"{app.proposal} {app.category}".lower()

    housing_words = (
        "dwelling",
        "dwellings",
        "homes",
        "housing",
        "residential",
        "apartments",
        "flats",
    )

    if not _contains_any(text, housing_words):
        return False

    numbers = [int(value) for value in re.findall(r"\b\d{2,4}\b", text)]
    return any(value >= 10 for value in numbers) or int(app.score or 0) >= 40


def _watchlist(applications):
    rules = (
        (
            "Major housing schemes",
            lambda app: _is_major_housing(app),
            "Larger residential proposals that may affect local services and infrastructure.",
        ),
        (
            "Battery storage projects",
            lambda app: _contains_any(
                f"{app.proposal} {app.category}".lower(),
                ("battery", "energy storage", "bess"),
            ),
            "Energy infrastructure proposals with potential strategic and community interest.",
        ),
        (
            "Solar and renewable energy",
            lambda app: _contains_any(
                f"{app.proposal} {app.category}".lower(),
                ("solar", "renewable", "photovoltaic", "wind turbine"),
            ),
            "Renewable-energy applications that may merit wider environmental coverage.",
        ),
        (
            "Commercial and employment sites",
            lambda app: _contains_any(
                f"{app.proposal} {app.category}".lower(),
                (
                    "commercial",
                    "employment",
                    "industrial",
                    "warehouse",
                    "retail",
                    "business unit",
                ),
            ),
            "Schemes that could affect jobs, investment, traffic or town-centre activity.",
        ),
        (
            "Heritage and listed buildings",
            lambda app: _contains_any(
                f"{app.proposal} {app.category}".lower(),
                ("listed building", "heritage", "conservation area"),
            ),
            "Applications involving protected buildings or conservation settings.",
        ),
        (
            "Telecommunications",
            lambda app: _contains_any(
                f"{app.proposal} {app.category}".lower(),
                ("telecom", "mast", "antenna", "5g"),
            ),
            "Mobile and communications infrastructure that can attract local interest.",
        ),
    )

    watch_items = []

    for title, matcher, description in rules:
        count = sum(1 for app in applications if matcher(app))
        if count:
            watch_items.append(
                {
                    "title": title,
                    "count": count,
                    "description": description,
                }
            )

    return watch_items


def _download_list(
    ui,
    scraper,
    list_type,
    wait_for_user,
    progress_start,
    progress_end,
):
    display_name = list_type.title()

    ui.write_log("")
    ui.write_log(f"Opening {display_name} Weekly List...")
    ui.set_status(f"Opening {display_name} weekly list")
    ui.set_current_application("Waiting for weekly list")
    ui.set_progress(progress_start, f"{display_name} Applications")

    scraper.open_weekly_list(
        list_type=list_type,
        wait_for_user=wait_for_user,
    )

    ui.write_log("Setting results per page to 100...")
    ui.set_status(f"Preparing {display_name} results")
    scraper.set_results_per_page()

    ui.write_log("Collecting application links...")
    ui.set_current_application("Collecting links")
    links = scraper.get_application_links()
    total = len(links)

    ui.write_log(f"{total} {list_type} applications found.")
    ui.set_list_progress(display_name, 0, total)

    downloaded = 0
    progress_span = progress_end - progress_start

    for counter, link in enumerate(links, start=1):
        if counter > 1 and (counter - 1) % 10 == 0:
            ui.write_log("Refreshing the Planning browser checkpoint...")
            scraper.restart_browser()
        ui.set_status(f"{display_name} {counter}/{total}")
        ui.set_current_application(
            f"{display_name} application {counter} of {total}"
        )
        ui.set_list_progress(display_name, counter, total)

        list_fraction = (counter - 1) / total if total > 0 else 1
        ui.set_progress(
            progress_start + (progress_span * list_fraction),
            f"{display_name} Applications",
        )

        ui.write_log(
            f"Downloading {list_type} application {counter} of {total}"
        )

        app = None
        for attempt in range(2):
            try:
                app = scraper.scrape_application(link)
                break
            except Exception as error:
                if attempt:
                    raise
                ui.write_log(
                    "Planning browser interrupted; restarting and retrying "
                    f"application {counter}..."
                )
                scraper.restart_browser()

        if app:
            scraper.applications.append(app)
            downloaded += 1

        completed_fraction = counter / total if total > 0 else 1
        ui.set_progress(
            progress_start + (progress_span * completed_fraction),
            f"{display_name} Applications",
        )

    ui.set_list_progress(display_name, total, total)
    return total, downloaded


def _save_source_cache(cache, source, applications, ui):
    try:
        cache.save(source.key, applications, datetime.now(timezone.utc))
    except Exception as error:
        ui.write_log(
            f"{source.name}: results collected, but its recovery cache could not be updated: "
            f"{_error_text(error)[:160]}"
        )


def _retain_cached_source(cache, source, scraper, result, ui):
    cached = cache.load(source.key)
    if not cached:
        result["status"] = "Failed"
        result["application_count"] = 0
        return False
    scraper.applications.extend(cached)
    result["status"] = "Retained"
    result["application_count"] = len(cached)
    ui.write_log(
        f"{source.name}: retained {len(cached)} applications from its last successful refresh."
    )
    return True


def run_weekly_download(ui):
    ui.write_log("")
    ui.write_log("========================================")
    ui.write_log("Planning Intelligence Started")
    ui.write_log("========================================")

    ui.set_progress(0.02, "Connecting")
    ui.set_status("Starting planning download")

    idox_sources = enabled_idox_sources()
    additional_sources = enabled_additional_sources()
    sources = [*idox_sources, *additional_sources]
    if not idox_sources:
        raise RuntimeError("No enabled Lincolnshire Idox planning sources are configured.")

    scraper = PlanningScraper(source=idox_sources[0])
    source_cache = PlanningSourceCache()

    try:
        decided_found = 0
        decided_downloaded = 0
        validated_found = 0
        validated_downloaded = 0
        source_results = []
        collection_start = 0.05
        collection_end = 0.86
        source_span = (collection_end - collection_start) / len(sources)

        for source_index, source in enumerate(idox_sources):
            if source_index:
                collected = list(scraper.applications)
                scraper.close()
                scraper = PlanningScraper(source=source)
                scraper.applications = collected
            else:
                scraper.set_source(source)
            source_start = collection_start + (source_span * source_index)
            source_midpoint = source_start + (source_span * 0.5)
            source_end = source_start + source_span

            ui.write_log("")
            ui.write_log(f"Connecting to {source.name}...")
            ui.set_status(f"Collecting {source.name}")
            ui.set_current_application(source.authority_label)

            result = {
                "key": source.key,
                "name": source.name,
                "authorities": list(source.authorities),
                "status": "Current",
                "error": "",
                "application_count": 0,
                "decided_found": 0,
                "decided_downloaded": 0,
                "validated_found": 0,
                "validated_downloaded": 0,
            }

            source_applications = []
            for attempt in range(3):
                applications_before_source = list(scraper.applications)
                try:
                    source_decided_found, source_decided_downloaded = _download_list(
                        ui=ui,
                        scraper=scraper,
                        list_type="decided",
                        wait_for_user=(source_index == 0 and attempt == 0),
                        progress_start=source_start,
                        progress_end=source_midpoint,
                    )
                    source_validated_found, source_validated_downloaded = _download_list(
                        ui=ui,
                        scraper=scraper,
                        list_type="validated",
                        wait_for_user=False,
                        progress_start=source_midpoint,
                        progress_end=source_end,
                    )
                except Exception as error:
                    scraper.applications = applications_before_source
                    if attempt < 2:
                        delay = 5 if attempt == 0 else 15
                        ui.write_log(
                            f"{source.name}: collection interrupted; retrying with a fresh "
                            f"browser in {delay} seconds ({attempt + 2}/3)..."
                        )
                        time.sleep(delay)
                        scraper.close()
                        scraper = PlanningScraper(source=source)
                        scraper.applications = applications_before_source
                        continue
                    result["error"] = _error_text(error)[:240]
                    ui.write_log(f"{source.name} failed: {result['error']}")
                    _retain_cached_source(
                        source_cache, source, scraper, result, ui
                    )
                    break
                else:
                    result["decided_found"] = source_decided_found
                    result["decided_downloaded"] = source_decided_downloaded
                    result["validated_found"] = source_validated_found
                    result["validated_downloaded"] = source_validated_downloaded
                    decided_found += source_decided_found
                    decided_downloaded += source_decided_downloaded
                    validated_found += source_validated_found
                    validated_downloaded += source_validated_downloaded
                    source_applications = scraper.applications[
                        len(applications_before_source):
                    ]
                    result["application_count"] = len(source_applications)
                    result["status"] = (
                        "Current" if source_applications else "Empty"
                    )
                    _save_source_cache(
                        source_cache, source, source_applications, ui
                    )
                    break

            source_results.append(result)

        for source_index, source in enumerate(
            additional_sources, start=len(idox_sources)
        ):
            source_start = collection_start + (source_span * source_index)
            source_end = source_start + source_span
            ui.write_log("")
            ui.write_log(f"Connecting to {source.name}...")
            ui.set_status(f"Collecting {source.name}")
            ui.set_current_application(source.authority_label)
            result = {
                "key": source.key,
                "name": source.name,
                "authorities": list(source.authorities),
                "status": "Current",
                "error": "",
                "application_count": 0,
                "decided_found": 0,
                "decided_downloaded": 0,
                "validated_found": 0,
                "validated_downloaded": 0,
            }
            try:
                if source.platform == "north_lincs_weekly":
                    ui.write_log(
                        "North Lincolnshire runs last and may open visible Chrome for verification."
                    )
                    ui.write_log(
                        "If prompted, complete the CAPTCHA within five minutes; collection will then continue automatically."
                    )
                    ui.set_status("Waiting up to five minutes for North Lincolnshire verification")
                applications = collect_additional_source(source) or []
                scraper.applications.extend(applications)
                count = len(applications)
                result["application_count"] = count
                result["status"] = "Current" if count else "Empty"
                _save_source_cache(source_cache, source, applications, ui)
                result["validated_found"] = count
                result["validated_downloaded"] = count
                validated_found += count
                validated_downloaded += count
                ui.write_log(f"{count} validated applications downloaded.")
                ui.set_progress(source_end, "Validated Applications")
                ui.set_list_progress("Validated", count, count)
            except Exception as error:
                result["error"] = _error_text(error)[:240]
                ui.write_log(f"{source.name} failed: {result['error']}")
                _retain_cached_source(
                    source_cache, source, scraper, result, ui
                )
            source_results.append(result)

        current_sources = sum(
            1 for result in source_results
            if result["status"] in {"Current", "Empty"}
        )
        retained_sources = sum(
            1 for result in source_results if result["status"] == "Retained"
        )
        failed_sources = sum(
            1 for result in source_results if result["status"] == "Failed"
        )
        completed_sources = current_sources + retained_sources
        if not scraper.applications:
            raise RuntimeError(
                "No current or retained Lincolnshire Planning applications were available."
            )
        ui.write_log("")
        ui.write_log(
            f"Source refresh summary: {current_sources} current, "
            f"{retained_sources} retained, {failed_sources} failed."
        )
        if retained_sources or failed_sources:
            ui.write_log(
                "The briefing will be updated with all available results; "
                "source status labels identify retained or unavailable data."
            )

        ui.set_progress(0.88, "Processing Results")
        ui.set_status("Removing duplicates")
        ui.set_current_application("Processing downloaded applications")
        ui.write_log("")
        ui.write_log("Removing duplicates...")

        before_deduplication = len(scraper.applications)
        scraper.remove_duplicates()
        duplicates_removed = before_deduplication - len(scraper.applications)

        ui.set_progress(0.91, "Processing Results")
        ui.set_status("Applying editorial intelligence")
        ui.write_log("Applying central editorial priorities...")

        priority_results = {}
        for app in scraper.applications:
            priority_results[id(app)] = _priority_for_application(app)

        ui.set_status("Sorting by editorial priority")
        ui.write_log("Sorting by editorial priority...")
        scraper.sort_by_score()

        ui.set_progress(0.94, "Saving Database")
        ui.set_status("Saving database")
        ui.set_current_application("Saving planning applications")
        ui.write_log("Saving database...")
        scraper.save_to_database()

        ui.set_progress(0.97, "Preparing Editorial Briefing")
        ui.set_status("Building editorial intelligence")
        ui.set_current_application("Preparing Version 3.1.1 briefing")

        total_db = total_applications()
        get_newsworthy()
        unique_total = len(scraper.applications)
        weekly_newsworthy = sum(
            1
            for app in scraper.applications
            if _is_newsworthy(priority_results[id(app)])
        )

        top_stories = [
            _application_to_dict(app)
            for app in scraper.applications[:TOP_STORY_LIMIT]
        ]

        all_applications = [
            _application_to_dict(app)
            for app in scraper.applications
        ]
        

        report_data = {
            "version": "3.1.1 Module Profiles",
            "applications_processed": unique_total,
            "newsworthy_stories": weekly_newsworthy,
            "duplicates_removed": duplicates_removed,
            "front_page_candidates": sum(
                1
                for app in scraper.applications
                if _is_front_page(priority_results[id(app)])
            ),
            "story_of_week": top_stories[0] if top_stories else None,
            "top_stories": top_stories,
            "all_applications": all_applications,
            "planning_sources": source_results,
            "planning_sources_completed": completed_sources,
            "planning_sources_configured": len(sources),
            "planning_sources_current": current_sources,
            "planning_sources_retained": retained_sources,
            "planning_sources_failed": failed_sources,
            "category_breakdown": _category_breakdown(scraper.applications),
            "area_breakdown": _hotspot_insight(_area_breakdown(scraper.applications)),
            "unavailable_area_count": _unavailable_area_count(scraper.applications),
            "authority_breakdown": _authority_breakdown(scraper.applications, sources),
            "watchlist": _watchlist(scraper.applications),
            "editorial_summary": editorial_summary(scraper.applications),
        }
        ui.set_report_data(report_data)
        ui.source_warning_count = retained_sources + failed_sources

        ui.downloaded.configure(
            text=f"Applications Downloaded : {unique_total}"
        )
        ui.newsworthiness.configure(
            text=f"Newsworthy Stories : {weekly_newsworthy}"
        )

        ui.write_log("")
        ui.write_log(f"{decided_found} decided applications discovered.")
        ui.write_log(f"{decided_downloaded} decided applications downloaded.")
        ui.write_log(f"{validated_found} validated applications discovered.")
        ui.write_log(f"{validated_downloaded} validated applications downloaded.")
        ui.write_log(f"{duplicates_removed} duplicate applications removed.")
        ui.write_log(f"{unique_total} unique applications processed.")
        ui.write_log(f"{weekly_newsworthy} weekly stories marked as newsworthy.")
        ui.write_log(
            f"Planning sources: {current_sources} current, "
            f"{retained_sources} retained, {failed_sources} failed."
        )
        ui.write_log(f"{total_db} applications currently stored.")
        ui.write_log("Story of the Week selected.")
        ui.write_log("Editorial priorities calculated.")
        ui.write_log("'Why it is news' explanations prepared.")
        ui.write_log("Story tags and redesigned story cards prepared.")
        ui.write_log("Follow-up recommendations prepared.")
        ui.write_log("Generate Story controls prepared for Version 2.3.")
        ui.write_log("Version 3.1.1 module-aware briefing prepared.")

        ui.set_progress(1, "Download Complete")
        if retained_sources or failed_sources:
            ui.set_status("Complete with source warnings")
            ui.set_current_application(
                f"{current_sources} current, {retained_sources} retained, "
                f"{failed_sources} failed"
            )
        else:
            ui.set_status("Complete")
            ui.set_current_application("Finished")

        return unique_total

    finally:
        scraper.close()
