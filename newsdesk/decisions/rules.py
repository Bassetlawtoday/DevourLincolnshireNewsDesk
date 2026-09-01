"""Editorial rules used by the decision engine."""

from __future__ import annotations


BREAKING_PRIMARY_CATEGORIES = {
    "Missing Person",
    "Major Incident",
    "Emergency",
}

IMMEDIATE_PUBLISH_PRIORITY = 90

HOMEPAGE_PRIORITY = 50

FACEBOOK_PRIORITY = 60

NEWSLETTER_PRIORITY = 20

EDITOR_REVIEW_CONFIDENCE = 0.50