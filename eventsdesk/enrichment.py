from __future__ import annotations

import re
from dataclasses import dataclass
from .models import EventRecord

COUNTIES = {
    "Nottinghamshire", "Derbyshire", "Leicestershire", "Lincolnshire", "Staffordshire",
    "Warwickshire", "Worcestershire", "Shropshire", "Northamptonshire", "Rutland", "West Midlands",
}

CITY_COUNTY = {
    "Nottingham": "Nottinghamshire", "Derby": "Derbyshire", "Leicester": "Leicestershire",
    "Lincoln": "Lincolnshire", "Mansfield": "Nottinghamshire", "Newark": "Nottinghamshire",
    "Retford": "Nottinghamshire", "Worksop": "Nottinghamshire", "Southwell": "Nottinghamshire",
    "Birmingham": "West Midlands", "Coventry": "West Midlands", "Dudley": "West Midlands",
    "Wolverhampton": "West Midlands", "Walsall": "West Midlands", "Solihull": "West Midlands",
    "Sandwell": "West Midlands", "Shrewsbury": "Shropshire", "Ludlow": "Shropshire",
    "Oswestry": "Shropshire", "Telford": "Shropshire", "Whitchurch": "Shropshire",
    "Bridgnorth": "Shropshire", "Market Drayton": "Shropshire", "Buxton": "Derbyshire",
    "Chesterfield": "Derbyshire", "Bakewell": "Derbyshire", "Matlock Bath": "Derbyshire",
    "Crich": "Derbyshire", "Bolsover": "Derbyshire", "Market Rasen": "Lincolnshire",
    "Boston": "Lincolnshire", "Grantham": "Lincolnshire", "Skegness": "Lincolnshire",
    "Spalding": "Lincolnshire", "Northampton": "Northamptonshire", "Corby": "Northamptonshire",
    "Kettering": "Northamptonshire", "Wellingborough": "Northamptonshire", "Malvern": "Worcestershire",
    "Worcester": "Worcestershire", "Bewdley": "Worcestershire", "Redditch": "Worcestershire",
    "Bromsgrove": "Worcestershire", "Rugby": "Warwickshire", "Warwick": "Warwickshire",
    "Kenilworth": "Warwickshire", "Stratford-upon-Avon": "Warwickshire", "Gaydon": "Warwickshire",
    "Hinckley": "Leicestershire", "Loughborough": "Leicestershire", "Melton": "Leicestershire",
    "Tamworth": "Staffordshire", "Stoke-on-Trent": "Staffordshire", "Newcastle-under-Lyme": "Staffordshire",
    "Stafford": "Staffordshire", "Lichfield": "Staffordshire", "Uttoxeter": "Staffordshire",
    "Rugeley": "Staffordshire", "Burton upon Trent": "Staffordshire",
}

# Area labels in the registry can describe districts as well as towns. Where there is a
# clear primary town, use it; otherwise retain the county only.
AREA_GEO = {
    "Bassetlaw": ("Worksop", "Nottinghamshire"), "Worksop / Bassetlaw": ("Worksop", "Nottinghamshire"),
    "Ashfield": (None, "Nottinghamshire"), "Gedling": (None, "Nottinghamshire"),
    "Broxtowe": (None, "Nottinghamshire"), "Rushcliffe": (None, "Nottinghamshire"),
    "Sherwood Forest": (None, "Nottinghamshire"), "Newark & Sherwood": ("Newark", "Nottinghamshire"),
    "Derbyshire / Peak District": (None, "Derbyshire"), "Amber Valley": (None, "Derbyshire"),
    "High Peak": (None, "Derbyshire"), "Derbyshire Dales": (None, "Derbyshire"),
    "Erewash": (None, "Derbyshire"), "North East Derbyshire": (None, "Derbyshire"),
    "Leicester & Leicestershire": ("Leicester", "Leicestershire"), "Charnwood": ("Loughborough", "Leicestershire"),
    "Harborough": (None, "Leicestershire"), "Hinckley & Bosworth": ("Hinckley", "Leicestershire"),
    "North West Leicestershire": (None, "Leicestershire"), "Blaby": (None, "Leicestershire"),
    "Oadby & Wigston": (None, "Leicestershire"), "Leicestershire / Lincolnshire fringe": (None, "Leicestershire"),
    "South Kesteven": ("Grantham", "Lincolnshire"), "North Kesteven": (None, "Lincolnshire"),
    "West Lindsey": (None, "Lincolnshire"), "East Lindsey": (None, "Lincolnshire"),
    "South Holland": ("Spalding", "Lincolnshire"), "North Northamptonshire": (None, "Northamptonshire"),
    "West Northamptonshire": ("Northampton", "Northamptonshire"), "Coventry / Warwickshire": ("Coventry", "West Midlands"),
    "Warwick District": ("Warwick", "Warwickshire"), "Stratford District": ("Stratford-upon-Avon", "Warwickshire"),
    "Cannock Chase": (None, "Staffordshire"), "East Staffordshire": ("Burton upon Trent", "Staffordshire"),
    "Staffordshire Moorlands": (None, "Staffordshire"), "Malvern Hills": ("Malvern", "Worcestershire"),
    "Wyre Forest": ("Bewdley", "Worcestershire"), "Wychavon": (None, "Worcestershire"),
    "Worcestershire / Shropshire": (None, "Worcestershire"), "Shropshire / Staffordshire": (None, "Shropshire"),
    "Birmingham / West Midlands": ("Birmingham", "West Midlands"),
}

SOURCE_GEO = {
    "Rock City": ("Rock City", "Nottingham", "Nottinghamshire", "NG1 5GG"),
    "Theatre Royal & Royal Concert Hall": ("Theatre Royal & Royal Concert Hall", "Nottingham", "Nottinghamshire", "NG1 5ND"),
    "Nottingham Playhouse": ("Nottingham Playhouse", "Nottingham", "Nottinghamshire", None),
    "Birmingham Rep": ("Birmingham Rep", "Birmingham", "West Midlands", "B1 2EP"),
    "Buxton Opera House": ("Buxton Opera House", "Buxton", "Derbyshire", "SK17 6XN"),
    "Derby Theatre": ("Derby Theatre", "Derby", "Derbyshire", "DE1 2NF"),
    "New Vic Theatre": ("New Vic Theatre", "Newcastle-under-Lyme", "Staffordshire", "ST5 0JG"),
    "Mansfield Palace Theatre": ("Mansfield Palace Theatre", "Mansfield", "Nottinghamshire", None),
    "De Montfort Hall": ("De Montfort Hall", "Leicester", "Leicestershire", None),
    "Curve Leicester": ("Curve", "Leicester", "Leicestershire", None),
    "Lichfield Garrick": ("Lichfield Garrick", "Lichfield", "Staffordshire", None),
    "Castle Theatre Wellingborough": ("Castle Theatre", "Wellingborough", "Northamptonshire", None),
    "Lighthouse Theatre Kettering": ("Lighthouse Theatre", "Kettering", "Northamptonshire", None),
}

# Ordered from specific to broad. Classification uses title + description + supplied venue,
# deliberately excluding source name so a theatre source does not force every record to Theatre.
CATEGORY_RULES = [
    ("Sport / Horse Racing", ("race day", "horse racing", "jockey club", "flat racing", "jump racing")),
    ("Sport / Cricket", ("cricket", "county championship", "t20", "one day cup", "the hundred", "vitality blast")),
    ("Sport / Football", ("football", "premier league", "efl", "fa cup", "league cup")),
    ("Sport / Rugby", ("rugby", "premiership rugby", "six nations")),
    ("Motorsport", ("motorsport", "motor racing", "superbike", "drag racing", "classic car")),
    ("Theatre / Pantomime", ("pantomime", "panto", "aladdin", "cinderella", "jack and the beanstalk", "snow white")),
    ("Theatre / Musical", ("musical", "blood brothers", "joseph and the amazing technicolor", "everybody's talking about jamie")),
    ("Theatre / Dance", ("ballet", "dance company", "contemporary dance", "ballroom")),
    ("Comedy", ("comedy", "comedian", "stand-up", "stand up", "comic ")),
    ("Music", ("concert", "live music", "gig", "orchestra", "tribute", "choir", "symphony", "jazz", "blues", "rock band")),
    ("Film", ("cinema", "film screening", "movie", "(12a)", "(15)", "(pg)", "(18)")),
    ("Family", ("family", "children", "kids", "toddler", "storytime", "santa")),
    ("Food & Drink", ("food festival", "food market", "street food", "beer festival", "wine tasting", "dining")),
    ("Heritage", ("heritage", "historic house", "castle tour", "history walk", "archaeology")),
    ("Exhibition", ("exhibition", "gallery", "art exhibition", "museum display")),
    ("Talk / Workshop", ("workshop", "lecture", "masterclass", "author talk", "in conversation")),
    ("Market / Fair", ("market", "craft fair", "antique fair", "makers fair")),
    ("Outdoor / Nature", ("guided walk", "nature walk", "wildlife", "birdwatch", "forest", "outdoor")),
    ("Festival", ("festival",)),
    ("Theatre", ("play by ", "a new play", "stage adaptation", "drama production", "matinee performance")),
]

SPORT_CATEGORY_SIGNALS = {
    "sport / horse racing": ("race day", "horse racing", "jockey club", "flat racing", "jump racing"),
    "sport / cricket": ("cricket", "county championship", "t20", "one day cup", "the hundred", "vitality blast"),
    "sport / football": ("football", "premier league", "efl", "fa cup", "league cup"),
    "sport / rugby": ("rugby", "premiership rugby", "six nations"),
}


def _has_category_signal(text: str, term: str) -> bool:
    """Match complete category terms, never fragments inside other words."""
    return bool(re.search(
        rf"(?<![a-z0-9]){re.escape(term.casefold())}(?![a-z0-9])",
        text,
    ))


def resolved_event_category(category, title=None, description=None, venue=None):
    """Validate supplied sport categories, then apply controlled inference."""
    hay = " ".join(str(x) for x in (title, description, venue) if x).casefold()
    supplied = str(category or "").strip()
    sport_signals = SPORT_CATEGORY_SIGNALS.get(supplied.casefold())
    if sport_signals and not any(_has_category_signal(hay, term) for term in sport_signals):
        supplied = ""
    if supplied:
        return supplied
    for inferred, terms in CATEGORY_RULES:
        if any(_has_category_signal(hay, term) for term in terms):
            return inferred
    return None


TYPE_FALLBACK = {
    "Music venue": "Music", "Concert hall": "Music", "Comedy listings": "Comedy", "Comedy aggregator": "Comedy",
    "Racecourse": "Sport / Horse Racing", "Motorsport venue": "Motorsport", "Gallery": "Exhibition",
    "Museum": "Exhibition", "Museum / gallery": "Exhibition", "Nature network": "Outdoor / Nature",
    "Country park": "Outdoor / Nature", "Equestrian aggregator": "Sport / Equestrian",
}

BAD_CATEGORY = re.compile(
    r"(?:\b(?:mon|tue|wed|thu|fri|sat|sun)\b.*\b20\d{2}\b|from:\s*£|more details|book now|\d{1,2}\s+(?:sep|oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug))",
    re.I,
)

@dataclass(frozen=True, slots=True)
class Quality:
    score: int
    status: str

class EventEnricher:
    def __init__(self, source_areas: dict[str, str | None] | None = None, source_types: dict[str, str | None] | None = None):
        self.source_areas = source_areas or {}
        self.source_types = source_types or {}

    def enrich(self, e: EventRecord) -> EventRecord:
        geo = SOURCE_GEO.get(e.source)
        if geo:
            venue, town, county, postcode = geo
            e.venue = e.venue or venue
            e.town = e.town or town
            e.county = e.county or county
            e.postcode = e.postcode or postcode

        area = (self.source_areas.get(e.source) or "").strip()
        if not e.town and area in CITY_COUNTY:
            e.town = area
        elif not e.town and area in AREA_GEO and AREA_GEO[area][0]:
            e.town = AREA_GEO[area][0]

        if not e.county:
            if e.town in CITY_COUNTY:
                e.county = CITY_COUNTY[e.town]
            elif area in COUNTIES:
                e.county = area
            elif area in AREA_GEO:
                e.county = AREA_GEO[area][1]

        # Repair common city/district values accidentally written into county.
        if e.county in CITY_COUNTY:
            e.county = CITY_COUNTY[e.county]
        elif e.county in AREA_GEO:
            e.county = AREA_GEO[e.county][1]

        if e.town:
            e.town = e.town.strip(" ,")
        if e.county:
            e.county = e.county.strip(" ,")

        hay = " ".join(x for x in (e.title, e.description, e.venue) if x).casefold()

        if e.category and (len(e.category) > 60 or BAD_CATEGORY.search(e.category)):
            e.category = None

        e.category = resolved_event_category(
            e.category, e.title, e.description, e.venue
        )

        if not e.category:
            e.category = TYPE_FALLBACK.get(self.source_types.get(e.source) or "")

        q = self.quality(e)
        e.quality_score = q.score
        e.quality_status = q.status
        e.raw = dict(e.raw or {})
        e.raw["enrichment"] = {"quality_score": q.score, "quality_status": q.status}
        return e.normalize()

    @staticmethod
    def quality(e: EventRecord) -> Quality:
        score = 30
        score += 20 if e.start else 0
        score += 10 if e.venue else 0
        score += 10 if e.town else 0
        score += 5 if e.county else 0
        score += 5 if e.category else 0
        score += 5 if e.description else 0
        score += 5 if e.image_url else 0
        score += 5 if e.event_url else 0
        score += 3 if e.price_text else 0
        score += 2 if e.postcode else 0
        score = min(score, 100)
        status = "complete" if score >= 85 else "usable" if score >= 65 else "limited" if score >= 45 else "review"
        return Quality(score, status)
