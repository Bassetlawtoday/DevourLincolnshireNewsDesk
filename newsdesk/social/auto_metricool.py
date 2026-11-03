"""Opt-in automatic delivery of Social Desk items as unpublished Metricool drafts."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import threading
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from newsdesk.social.metricool import MetricoolClient
from newsdesk.social.store import SocialDraftStore, SocialSettingsStore
from newsdesk.social.text import compose_metricool_text


LOG = logging.getLogger(__name__)
CONFIG_PATH = Path("data") / "social" / "auto_metricool.json"
_LOCK = threading.RLock()


def load_auto_config() -> dict:
    defaults = {"enabled": False, "providers": [], "delay_hours": 24}
    try:
        # Windows PowerShell 5 writes UTF-8 JSON with a BOM.
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return defaults
    providers = [
        str(item).strip().casefold()
        for item in value.get("providers", [])
        if str(item).strip()
    ]
    return {
        "enabled": value.get("enabled") is True,
        "providers": list(dict.fromkeys(providers)),
        "delay_hours": 24,
    }


def _future_datetime(timezone_name: str) -> str:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("Europe/London")
    return (datetime.now(timezone) + timedelta(hours=24)).replace(
        microsecond=0
    ).strftime("%Y-%m-%dT%H:%M:%S")


def _find(drafts, draft_id):
    return next((item for item in drafts if item.draft_id == draft_id), None)


def _save_state(draft_id: str, state: str, *, status: str, error: str = "", metricool_id: str = ""):
    with _LOCK:
        store = SocialDraftStore()
        drafts = store.load()
        draft = _find(drafts, draft_id)
        if draft is None:
            return
        draft.metricool_auto_state = state
        draft.metricool_auto_error = error[:1000]
        if metricool_id:
            draft.metricool_id = metricool_id
        draft.status = status
        draft.updated_at = datetime.now().astimezone().isoformat()
        store.save(drafts)


def queue_auto_metricool_handoff(draft_id: str) -> bool:
    """Queue one local draft if the operator explicitly enabled this test."""
    config = load_auto_config()
    if not config["enabled"]:
        return False
    with _LOCK:
        store = SocialDraftStore()
        drafts = store.load()
        draft = _find(drafts, draft_id)
        if draft is None or draft.metricool_id:
            return False
        if draft.metricool_auto_state in {"queued", "sending", "sent"}:
            return False
        draft.metricool_auto_state = "queued"
        draft.metricool_auto_error = ""
        draft.status = "Waiting for automatic Metricool draft handoff"
        draft.updated_at = datetime.now().astimezone().isoformat()
        store.save(drafts)
    threading.Thread(
        target=_deliver,
        args=(draft_id,),
        name=f"metricool-auto-{draft_id[:8]}",
        daemon=True,
    ).start()
    return True


def _deliver(draft_id: str) -> None:
    try:
        config = load_auto_config()
        if not config["enabled"]:
            _save_state(draft_id, "disabled", status="Local draft — automatic Metricool handoff disabled")
            return
        settings = SocialSettingsStore().load()
        required = (settings.get("token"), settings.get("user_id"), settings.get("blog_id"))
        if not all(required):
            raise RuntimeError("Metricool settings are not complete")
        connected = {
            item.strip().casefold()
            for item in settings.get("connected_networks", "").split(",")
            if item.strip()
        }
        requested = [item for item in config["providers"] if item in connected]
        if not requested:
            raise RuntimeError("none of the selected automatic networks are connected")
        with _LOCK:
            store = SocialDraftStore()
            drafts = store.load()
            draft = _find(drafts, draft_id)
            if draft is None or draft.metricool_id:
                return
            draft.metricool_auto_state = "sending"
            draft.status = "Creating unpublished Metricool draft"
            draft.publication_datetime = _future_datetime(
                settings.get("timezone") or draft.timezone or "Europe/London"
            )
            draft.timezone = settings.get("timezone") or draft.timezone or "Europe/London"
            store.save(drafts)

        # Transfer every available image to the unpublished Metricool draft.
        # Rights/credit review remains an editorial decision inside Metricool.
        has_image = bool(draft.image_url or draft.local_image_path)
        providers = list(requested)
        if "instagram" in providers and not has_image:
            providers.remove("instagram")
        if not providers:
            raise RuntimeError("the selected networks require an approved credited image")
        outgoing = compose_metricool_text(
            draft.text,
            source_url=draft.source_url if draft.include_source_url else "",
            image_caption=draft.image_caption if has_image else "",
            image_credit=draft.image_credit if has_image else "",
            instagram_hashtags=(
                draft.instagram_hashtags if "instagram" in providers else ""
            ),
        )
        client = MetricoolClient(
            token=settings["token"],
            user_id=settings["user_id"],
            blog_id=settings["blog_id"],
        )
        result = client.create_draft(
            text=outgoing,
            providers=providers,
            publication_datetime=draft.publication_datetime,
            timezone=draft.timezone,
            image_url=draft.image_url if has_image else "",
            image_path=draft.local_image_path if has_image else "",
        )
        identifier = MetricoolClient.draft_id(result)
        note = f"Automatic NewsDesk handoff. Source module: {draft.source_kind or 'unknown'}."
        if identifier:
            try:
                client.add_private_note(identifier, note)
            except Exception:
                LOG.exception("Metricool draft %s created but private note failed", identifier)
        _save_state(
            draft_id,
            "sent",
            status="Sent automatically to Metricool as unpublished draft",
            metricool_id=identifier,
        )
    except Exception as exc:
        LOG.exception("Automatic Metricool handoff failed for %s", draft_id)
        _save_state(
            draft_id,
            "failed",
            status="Automatic Metricool handoff failed — retained locally",
            error=str(exc),
        )


__all__ = ["load_auto_config", "queue_auto_metricool_handoff"]
