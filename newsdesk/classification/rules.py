"""
Editorial classification rules for Devour Lincolnshire NewsDesk.

This module contains all of the editorial knowledge used by the
StoryClassifier. The classifier itself contains no hard-coded
categories or keywords – it simply scores these rules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------
# Category Rules
# ---------------------------------------------------------------------

CATEGORY_RULES = {

    "Court": {
        "priority": 75,
        "keywords": {
            "court": 8,
            "magistrates": 8,
            "crown court": 10,
            "judge": 8,
            "jailed": 10,
            "sentenced": 10,
            "sentence": 8,
            "convicted": 10,
            "guilty": 8,
            "pleaded guilty": 10,
            "pleaded": 6,
            "appeared in court": 10,
            "prison": 7,
            "custody": 6,
        },
    },

    "Drugs": {
        "priority": 70,
        "keywords": {
            "drug": 6,
            "drugs": 6,
            "cannabis": 10,
            "cocaine": 10,
            "heroin": 10,
            "amphetamine": 8,
            "ecstasy": 8,
            "ketamine": 8,
            "factory": 4,
            "grow": 5,
            "grow house": 8,
            "cultivation": 8,
            "production": 5,
            "dealing": 8,
            "dealer": 8,
            "seized": 3,
        },
    },

    "Roads": {
        "priority": 65,
        "keywords": {
            "collision": 10,
            "crash": 10,
            "rtc": 10,
            "road traffic collision": 12,
            "vehicle": 5,
            "car": 4,
            "van": 4,
            "lorry": 5,
            "motorbike": 5,
            "traffic": 5,
            "road closed": 8,
            "lane closed": 7,
            "a1": 4,
            "a57": 4,
            "a614": 4,
            "m1": 4,
        },
    },

    "Fire": {
        "priority": 70,
        "keywords": {
            "fire": 10,
            "blaze": 10,
            "firefighters": 8,
            "firefighter": 8,
            "fire crew": 8,
            "crew": 4,
            "smoke": 6,
            "rescue": 7,
            "burning": 7,
        },
    },

    "Appeal": {
        "priority": 90,
        "keywords": {
            "appeal": 10,
            "appealing": 6,
            "witness": 8,
            "witnesses": 8,
            "information": 4,
            "dashcam": 8,
            "cctv": 8,
            "identify": 8,
            "recognise": 8,
            "recognize": 8,
            "trace": 7,
        },
    },

    "Missing Person": {
        "priority": 100,
        "keywords": {
            "missing": 10,
            "last seen": 10,
            "found safe": 10,
            "high risk": 8,
            "concern": 8,
            "welfare": 5,
        },
    },

    "Burglary": {
        "priority": 70,
        "keywords": {
            "burglary": 10,
            "burglar": 8,
            "break in": 7,
            "broke into": 7,
            "forced entry": 6,
        },
    },

    "Fraud": {
        "priority": 65,
        "keywords": {
            "fraud": 10,
            "scam": 8,
            "romance fraud": 10,
            "bank scam": 10,
            "investment fraud": 10,
            "phishing": 8,
        },
    },

    "Weapons": {
        "priority": 75,
        "keywords": {
            "knife": 8,
            "weapon": 7,
            "firearm": 10,
            "gun": 10,
            "shotgun": 10,
            "ammunition": 8,
        },
    },

    "Business": {
        "priority": 35,
        "keywords": {
            "business": 6,
            "company": 5,
            "investment": 8,
            "jobs": 8,
            "employment": 8,
            "economy": 6,
            "funding": 6,
        },
    },

    "Council": {
        "priority": 35,
        "keywords": {
            "council": 10,
            "councillor": 8,
            "cabinet": 7,
            "consultation": 7,
            "planning": 7,
            "borough": 4,
            "district council": 8,
        },
    },

    "Health": {
        "priority": 45,
        "keywords": {
            "nhs": 10,
            "hospital": 8,
            "ambulance": 8,
            "health": 6,
            "patient": 6,
        },
    },

    "Education": {
        "priority": 35,
        "keywords": {
            "school": 8,
            "college": 8,
            "academy": 7,
            "students": 6,
            "education": 6,
        },
    },

    "Community": {
        "priority": 30,
        "keywords": {
            "community": 8,
            "charity": 7,
            "volunteers": 7,
            "fundraiser": 7,
            "fundraising": 7,
        },
    },

    "Environment": {
        "priority": 30,
        "keywords": {
            "environment": 8,
            "recycling": 7,
            "wildlife": 7,
            "nature": 6,
            "climate": 7,
        },
    },

    "Sport": {
        "priority": 25,
        "keywords": {
            "football": 8,
            "rugby": 8,
            "cricket": 8,
            "match": 5,
            "club": 5,
            "league": 5,
        },
    },

    "Events": {
        "priority": 20,
        "keywords": {
            "festival": 8,
            "event": 6,
            "concert": 8,
            "show": 5,
            "celebration": 5,
            "market": 5,
        },
    },

    "Weather": {
        "priority": 40,
        "keywords": {
            "weather": 8,
            "storm": 10,
            "snow": 8,
            "ice": 7,
            "heatwave": 8,
            "flood": 10,
        },
    },

}

# ---------------------------------------------------------------------
# Breaking News Triggers
# ---------------------------------------------------------------------

BREAKING_KEYWORDS = {
    "murder",
    "fatal",
    "terrorism",
    "armed police",
    "major incident",
    "explosion",
    "evacuated",
    "missing",
    "found dead",
    "serious collision",
}

# ---------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------

DEFAULT_CATEGORY = "Other"

DEFAULT_PRIORITY = 25

MINIMUM_SCORE = 5