"""Offline mobile-news payload preparation. No network publishing."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone


def ready_payload(article):
    """Prepare a single approved story; never expose unpublished source copy."""
    if (article.status or "").lower() != "ready":
        raise ValueError("Only Ready articles may be exported")
    if not article.title.strip() or not article.body.strip():
        raise ValueError("Headline and body are required")
    return {
        "schema_version": 1,
        "article_id": article.article_id,
        "headline": article.title.strip(),
        "body": article.body.strip(),
        "county": article.county or "Lincolnshire",
        "areas": list(article.areas or []),
        "category": article.category.strip(),
        "image": {
            "url": article.image_url.strip(),
            "caption": article.image_caption.strip(),
            "credit": article.image_credit.strip(),
        },
        "source": {"name": article.source, "url": article.source_url},
        "notification": {
            "requested": bool(article.notify_readers),
            "type": article.notification_type,
            "message": article.notification_message,
        },
        "editorial_status": "ready",
        "updated_at": article.updated_at,
    }


def build_export(articles):
    ready = [ready_payload(a) for a in articles if (a.status or "").lower() == "ready"]
    return {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_preview_not_published",
        "articles": ready,
    }


def write_export(articles, destination):
    """Write offline preview JSON only; never upload or publish."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = build_export(articles)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload["articles"])
