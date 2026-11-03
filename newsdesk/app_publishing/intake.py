"""Independent NewsDesk-to-App-Publishing intake.

No Social Desk or Metricool calls are made here.
"""
from __future__ import annotations

import hashlib

from newsdesk.app_publishing.store import AppArticleStore
from newsdesk.social.content_gate import has_verified_full_content


SUPPORTED_MODULES = frozenset({"police", "council", "sport", "content"})


def story_identity(story, module_key: str) -> str:
    """Stable identity based on module and source ID or source URL.

    Headline and article text are deliberately excluded so editorial/source
    corrections do not create a second article.
    """
    source_key = str(getattr(story, "story_id", "") or getattr(story, "url", "") or "").strip()
    if not source_key:
        raise ValueError("A story ID or source URL is required for app intake")
    raw = f"{module_key.strip().casefold()}|{source_key.casefold()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stage_app_story(story, *, module_key: str, store: AppArticleStore | None = None):
    """Stage a verified full article once, preserving existing editorial edits.

    Returns (article_or_none, was_created). An incomplete article is skipped.
    """
    key = str(module_key or "").strip().casefold()
    if key not in SUPPORTED_MODULES:
        return None, False
    if not str(getattr(story, "title", "") or "").strip():
        return None, False
    if not has_verified_full_content(key, story):
        return None, False
    store = store or AppArticleStore()
    return store.stage_story(story, source_identity=story_identity(story, key))


def stage_app_payload(payload: dict, *, module_key: str, store: AppArticleStore | None = None) -> int:
    """Stage verified full stories from a collection result.

    The caller controls when this is invoked; no refresh hooks are installed.
    """
    store = store or AppArticleStore()
    count = 0
    for story in payload.get("stories") or []:
        _article, created = stage_app_story(story, module_key=module_key, store=store)
        count += int(created)
    return count
