"""Bounded, in-process cache for lazily prepared editorial image previews."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Optional

from PIL import Image


DEFAULT_THUMBNAIL_CACHE_LIMIT = 24


class ImagePreviewCache:
    """Cache decoded and resized PIL previews without retaining source images."""

    def __init__(self, max_entries: int = DEFAULT_THUMBNAIL_CACHE_LIMIT):
        if max_entries < 1:
            raise ValueError("max_entries must be at least one")
        self.max_entries = max_entries
        self._items: OrderedDict[tuple[object, ...], Image.Image] = OrderedDict()
        self._lock = RLock()
        self.hits = 0
        self.misses = 0

    def get(
        self,
        path: str | Path,
        size: tuple[int, int],
        *,
        allow_upscale: bool = False,
    ) -> Optional[Image.Image]:
        """Return a prepared preview, or ``None`` for a missing/invalid image."""

        image_path = Path(path)
        try:
            stat = image_path.stat()
        except OSError:
            return None

        key = (
            str(image_path.resolve()),
            stat.st_mtime_ns,
            stat.st_size,
            size,
            allow_upscale,
        )
        with self._lock:
            cached = self._items.get(key)
            if cached is not None:
                self._items.move_to_end(key)
                self.hits += 1
                return cached

        try:
            with Image.open(image_path) as source_image:
                preview = source_image.convert("RGB")
                if allow_upscale:
                    source_width, source_height = preview.size
                    if source_width <= 0 or source_height <= 0:
                        return None
                    scale = min(size[0] / source_width, size[1] / source_height)
                    target = (
                        max(1, int(source_width * scale)),
                        max(1, int(source_height * scale)),
                    )
                    preview = preview.resize(target, Image.Resampling.LANCZOS)
                else:
                    preview.thumbnail(size, Image.Resampling.LANCZOS)
                prepared = preview.copy()
        except (OSError, ValueError):
            return None

        with self._lock:
            self.misses += 1
            self._items[key] = prepared
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
        return prepared

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


IMAGE_PREVIEW_CACHE = ImagePreviewCache()

