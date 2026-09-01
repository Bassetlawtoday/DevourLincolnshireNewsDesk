"""
Shared application constants for Devour Lincolnshire NewsDesk.
"""

from __future__ import annotations

APP_NAME = "Devour Lincolnshire NewsDesk"

VERSION = "1.0"

# ------------------------------------------------------------------
# Story priorities
# ------------------------------------------------------------------

PRIORITY_IMMEDIATE = "Immediate"

PRIORITY_URGENT = "Urgent"

PRIORITY_ROUTINE = "Routine"

PRIORITY_LOW = "Low"

PRIORITIES = (
    PRIORITY_IMMEDIATE,
    PRIORITY_URGENT,
    PRIORITY_ROUTINE,
    PRIORITY_LOW,
)

# ------------------------------------------------------------------
# Editorial decisions
# ------------------------------------------------------------------

DECISION_PUBLISH = "Publish"

DECISION_REVIEW = "Review"

DECISION_HOLD = "Hold"

DECISIONS = (
    DECISION_PUBLISH,
    DECISION_REVIEW,
    DECISION_HOLD,
)

# ------------------------------------------------------------------
# Output formats
# ------------------------------------------------------------------

OUTPUT_WEBSITE = "website"

OUTPUT_FACEBOOK = "facebook"

OUTPUT_NEWSLETTER = "newsletter"

OUTPUT_METADATA = "metadata"

OUTPUT_BREAKING = "breaking"

OUTPUTS = (
    OUTPUT_WEBSITE,
    OUTPUT_FACEBOOK,
    OUTPUT_NEWSLETTER,
    OUTPUT_METADATA,
    OUTPUT_BREAKING,
)

# ------------------------------------------------------------------
# Default editorial limits
# ------------------------------------------------------------------

FACEBOOK_MAX_EMOJIS = 10

FACEBOOK_MAX_LENGTH = 5000

NEWSLETTER_SUMMARY_LENGTH = 250

SEO_TITLE_LENGTH = 60

META_DESCRIPTION_LENGTH = 155