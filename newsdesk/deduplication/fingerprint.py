"""Generate fingerprints for articles."""

from __future__ import annotations

import hashlib
import re

_NORMALISE = re.compile(r"[^\w\s]")


def fingerprint(*parts: str) -> str:
    """Return a stable fingerprint for an article."""

    text = " ".join(parts)

    text = text.casefold()

    text = _NORMALISE.sub("", text)

    text = " ".join(text.split())

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()