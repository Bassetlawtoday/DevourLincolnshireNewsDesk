"""Editorial completeness checks for Updates Desk stories."""

from __future__ import annotations

import re

from newsdesk.story import Story


MIN_FULL_CONTENT_CHARS = 120
MIN_ADDITIONAL_CHARS = 40


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_materially_full(story: Story, *, teaser: str = "") -> bool:
    """Return True only when a story contains substantive article copy.

    Images, metadata and a feed teaser are never sufficient.  When the
    original teaser is known, fetched text must materially exceed it.
    """

    body = _normalise(story.body)
    summary = _normalise(teaser or story.summary)
    if len(body) < MIN_FULL_CONTENT_CHARS:
        return False
    if summary:
        if body.casefold() == summary.casefold():
            return False
        if len(body) < len(summary) + MIN_ADDITIONAL_CHARS:
            return False
    return True


def has_verified_full_content(module_key: str, story: Story) -> bool:
    """Return whether Updates Desk may release this story to Social Desk."""

    extras = story.extras or {}
    key = str(module_key or "").strip().casefold()
    if key == "content":
        return bool(extras.get("detail_complete")) and is_materially_full(story)
    if key == "sport":
        return (
            str(extras.get("article_content_status", "")).casefold() == "complete"
            and is_materially_full(story)
        )
    if extras.get("updates_full_content_verified"):
        return is_materially_full(story)
    if extras.get("content_completeness") == "summary_only":
        return False
    # Police, Fire and Council collectors normally supply their complete body
    # during refresh.  It must still pass the substantive-copy boundary.
    return key in {"police", "fire", "council"} and is_materially_full(story)


__all__ = ["has_verified_full_content", "is_materially_full"]
