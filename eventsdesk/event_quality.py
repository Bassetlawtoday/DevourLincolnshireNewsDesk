from __future__ import annotations

import re
import urllib.parse
from collections import Counter
from typing import Iterable
from urllib.parse import urlsplit

from .models import EventRecord

_CTA_PATTERNS = (
    r"^booking(?:\s+and)?\s+more\s+information$",
    r"^more\s+information$",
    r"^more\s+info$",
    r"^find\s+out\s+more(?:\s*[-–—:]\s*)?$",
    r"^read\s+more$",
    r"^book\s+now$",
    r"^book\s+tickets?$",
    r"^buy\s+tickets?$",
    r"^quick\s+book$",
    r"^tickets?$",
    r"^details?$",
    r"^view\s+event$",
    r"^view\s+details?$",
)
_CTA_RE = re.compile("(?:" + "|".join(_CTA_PATTERNS) + ")", re.I)

# Generic navigation/service/news headings that are not useful event titles even
# when a nearby publication date is accidentally interpreted as an event date.
_GENERIC_NON_EVENT_PATTERNS = (
    r"^latest\s+news$",
    r"^recent\s+news(?:\s+see\s+all)?$",
    r"^news$",
    r"^our\s+services$",
    r"^how\s+can\s+we\s+help\s+you\s+today\??$",
    r"^elections?\s*(?:&|and)\s*voting$",
    r"^elections?\s+and\s+referendum\s+results$",
    r"^for\s+you$",
    r"^welcome\s+to\s+[^.!?]+$",
    r"^plan\s+your\s+visit$",
    r"^noticeboard$",
    r"^view\s+fixture$",
    r"^secure\s+my\s+booking$",
    r"^highlights?$",
    r"^visit$",
    r"^pay\s+for\s+it$",
    r"^what(?:'|’)?s\s+on$",
    r"^what(?:'|’)?s\s+on\s+at\s+[^.!?]+$",
    r"^ards\s+testing(?:\s+.+)?$",
    r"^20\d{2}\s+upcoming\s+events$",
    r"^about\s+this\s+venue$",
    r"^coming\s+soon(?:\s+to\s+.+)?$",
    r"^filter\s+by\s+date\s+range$",
    r"^join\s+the\s+conversation$",
    r"^look\s+for\s+it$",
    r"^quick\s+buy$",
    r"^search$",
    r"^categories$",
    r"^custom\s+date\s+range$",
    r"^filter\s+our\s+events$",
    r"^coming\s+up\s+next$",
    r"^recently\s+added$",
    r"^upcoming\s+events$",
    r"^latest\s+events$",
    r"^listings?\s+\d{1,2}\s*[-–—]\s*\d{1,2}\s+[a-z]+(?:\s+20\d{2})?$",
    r"^today\s*[-–—]\s*(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$",
    r"^upcoming\s+screenings?$",
    r"^indie\s+wednesdays?\s+\d{8}(?:\s+\d{8})?$",
    r"^event\s+highlights$",
    r"^what(?:'|’)?s\s+on\s+news$",
    r"^pin\s+it\s+on\s+pinterest$",
    r"^keep\s+up\s+to\s+date\s+with\s+the\s+project$",
    r"^sign\s+up.*$",
    r"^stay\s+up\s+to\s+date$",
    r"^stay\s+in\s+the\s+loop$",
    r"^subscribe\s+to\s+our\s+newsletters?$",
    r"^newsletter\s+sign[- ]up$",
    r"^join\s+our\s+mailing\s+list$",
    r"^please\s+complete\s+the\s+captcha$",
    r"^box\s+office\s+\d.*$",
    r"^rentals\s+and\s+lets$",
    r"^follow\s+thoresby$",
    r"^explore\s+thoresby$",
    r"^explore$",
    r"^activities\s+at\s+thoresby$",
    r"^main\s+house$",
    r"^main\s+stage$",
    r"^nottinghamshire\s+membership$",
    r"^useful\s+links$",
    r"^small\s+print$",
    r"^find\s+us$",
    r"^(?:facebook|instagram|twitter)$",
    r"^stay\s+in\s+touch\s+by\s+signing\s+up\s+to\s+our\s+mailing\s+list$",
    r"^sign\s+up\s+to\s+our\s+newsletter$",
    r"^the\s+stage\s+is\s+set$",
    r"^opening\s+times?$",
    r"^social\s+media$",
    r"^filter\s+events?$",
    r"^filter\s+by$",
    r"^news\s*(?:&|and)\s*blogs?$",
    r"^all\s+events?$",
    r"^featured\s+shows?$",
    r"^gallery\s+shop$",
    r"^our\s+supporters$",
    r"^welcome$",
    r"^playbill$",
    r"^event\s+details:?\s*$",
    r"^(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2}$",
)
_GENERIC_NON_EVENT_RE = re.compile("(?:" + "|".join(_GENERIC_NON_EVENT_PATTERNS) + ")", re.I)

# Strong event-language signals. A news article can legitimately be the only
# source for an event announcement, so news URLs are retained when the title
# itself clearly describes an event/activity.
_EVENT_SIGNAL_RE = re.compile(
    r"\b(?:event|festival|fair|fayre|workshop|concert|gig|show|theatre|theater|"
    r"cinema|film|screening|exhibition|market|open\s+day|raceday|race|fixture|"
    r"match|game|class|session|course|tour|guided\s+walk|walks|talk|lecture|conference|meeting|"
    r"launch|celebration|party|gala|performance|pantomime|musical|comedy|dance|"
    r"family\s+fun|book\s+club|heritage\s+open|activity|activities)\b",
    re.I,
)

_NEWS_PATH_SEGMENTS = (
    "/news/",
    "/latest-news/",
    "/press/",
    "/press-releases/",
    "/newsroom/",
    "/media-centre/",
    "/media-center/",
)


def normalized_title(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def is_cta_title(value: str | None) -> bool:
    title = normalized_title(value)
    return bool(title and _CTA_RE.fullmatch(title))


def is_generic_non_event_title(value: str | None) -> bool:
    title = normalized_title(value)
    return bool(title and _GENERIC_NON_EVENT_RE.fullmatch(title))


def has_event_signal(value: str | None) -> bool:
    return bool(_EVENT_SIGNAL_RE.search(normalized_title(value)))


def is_news_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        path = (urlsplit(value).path or "/").casefold()
    except Exception:
        path = str(value).casefold()
    return any(segment in path for segment in _NEWS_PATH_SEGMENTS)


def is_probable_non_event(event: EventRecord) -> bool:
    """Conservatively identify obvious false positives.

    We remove generic navigation/service headings outright. For news/press URLs,
    we only remove the record when the title has no recognisable event signal.
    This keeps legitimate announcement articles such as a festival launch or
    community event while suppressing ordinary council/news stories whose
    publication date was mistaken for an event date.
    """
    if is_cta_title(event.title) or is_generic_non_event_title(event.title):
        return True

    if is_news_url(event.event_url) and not has_event_signal(event.title):
        return True

    return False


def filter_false_events(events: Iterable[EventRecord]) -> tuple[list[EventRecord], int]:
    kept: list[EventRecord] = []
    removed = 0
    for event in events:
        if is_probable_non_event(event):
            removed += 1
            continue
        kept.append(event)
    return kept, removed


def repeated_title_anomalies(events: Iterable[EventRecord]) -> list[dict]:
    """Report suspiciously dominant titles without deleting legitimate repeats.

    The report is diagnostic only. A long theatre run such as Aladdin can safely
    appear many times; a title is flagged only when it dominates a source output
    at scale, or when it is an obvious false-positive title.
    """
    rows = list(events)
    if not rows:
        return []
    counts = Counter(normalized_title(e.title) for e in rows if normalized_title(e.title))
    out: list[dict] = []
    total = len(rows)
    for title, count in counts.most_common():
        share = count / total
        if is_cta_title(title) or is_generic_non_event_title(title) or (count >= 100 and share >= 0.35):
            out.append({"title": title, "count": count, "share": round(share, 4)})
    return out

def _slug_title(slug: str) -> str:
    text = urllib.parse.unquote(slug or "").strip(" /")
    text = re.sub(r"[-_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    return " ".join(word if word.isupper() else word.capitalize() for word in text.split())


def repaired_event_title(title: str | None, source: str | None, event_url: str | None) -> str:
    raw = normalized_title(title) or "Event"
    source_name = normalized_title(source)
    url = (event_url or "").strip()
    if not url:
        return raw
    try:
        path = [p for p in urllib.parse.urlsplit(url).path.split("/") if p]
    except Exception:
        return raw
    slug = ""
    source_key = source_name.casefold()

    if source_key == "notts.com" and len(path) >= 3 and path[0].casefold() == "venues":
        # /venues/<venue>/<event-slug>[/date]
        slug = path[2]

    elif source_key == "the deco theatre":
        generic = raw.casefold().replace("\\'", "'")
        if generic in {"what's on & tickets", "what’s on & tickets"}:
            # /event/<event-slug>
            for i, part in enumerate(path):
                if part.casefold() == "event" and i + 1 < len(path):
                    slug = path[i + 1]
                    break

    elif source_key == "curve leicester":
        # /whats-on/shows/<event-slug>
        if len(path) >= 3 and path[0].casefold() == "whats-on" and path[1].casefold() == "shows":
            slug = path[2]

    elif source_key in {"royal & derngate", "the core at corby cube"}:
        # /whats-on/<event-slug>
        if len(path) >= 2 and path[0].casefold() == "whats-on":
            slug = path[1]

    elif source_key == "derby theatre":
        # /event/<event-slug>
        if len(path) >= 2 and path[0].casefold() == "event":
            slug = path[1]

    elif source_key == "woodland trust":
        # /visiting-woods/things-to-do/events/<event-slug>
        for i, part in enumerate(path):
            if part.casefold() == "events" and i + 1 < len(path):
                slug = path[i + 1]
                break
    elif source_key == "stafford borough council" and raw.casefold() == "events":
        for i, part in enumerate(path):
            if part.casefold() == "event" and i + 1 < len(path):
                slug = path[i + 1]
                break

    repaired = _slug_title(slug)
    return repaired or raw
