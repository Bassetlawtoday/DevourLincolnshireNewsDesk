"""Focused lifecycle helpers shared by intelligence module windows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import sys
from typing import Any


DEFAULT_SEARCH_DEBOUNCE_MS = 180


def resolve_window(owner):
    """Return the Tk window represented by a window or lightweight wrapper."""

    return getattr(owner, "window", owner)


def window_is_live(owner) -> bool:
    if owner is None:
        return False
    try:
        return bool(resolve_window(owner).winfo_exists())
    except Exception:
        return False


def _available_desktop(window) -> tuple[int, int, int, int]:
    """Return the usable desktop rectangle in Tk coordinate units.

    On Windows, SPI_GETWORKAREA excludes the taskbar.  The scale conversion
    keeps the rectangle compatible with Tk when Windows display scaling is in
    use.  Other platforms retain a conservative bottom reserve.
    """

    screen_width = max(1, int(window.winfo_screenwidth()))
    screen_height = max(1, int(window.winfo_screenheight()))

    if sys.platform == "win32":
        try:
            import ctypes

            class Rect(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = Rect()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                physical_width = max(1, int(rect.right - rect.left))
                scale = physical_width / screen_width
                if 0.75 <= scale <= 3.0:
                    return (
                        round(rect.left / scale),
                        round(rect.top / scale),
                        round(physical_width / scale),
                        round((rect.bottom - rect.top) / scale),
                    )
        except Exception:
            pass

    reserved_bottom = max(64, round(screen_height * 0.06))
    return 0, 0, screen_width, max(1, screen_height - reserved_bottom)


def maximize_window(owner) -> bool:
    """Fit a Tk window inside the usable desktop, clear of the taskbar."""

    window = resolve_window(owner)
    try:
        window.update_idletasks()
        left, top, width, height = _available_desktop(window)
        margin = 8
        width = max(1, width - (margin * 2))
        height = max(1, height - (margin * 2))
        window.geometry(f"{width}x{height}+{left + margin}+{top + margin}")
        window.update_idletasks()
        window.deiconify()
        return True
    except Exception:
        return False


def focus_existing_window(owner) -> bool:
    """Focus a live owned window and report whether it could be reused."""

    if not window_is_live(owner):
        return False
    window = resolve_window(owner)
    window.deiconify()
    maximize_window(window)
    window.lift()
    window.focus_force()
    return True


def present_window_foreground(
    owner, *, temporary_topmost=False, maximized=False
) -> None:
    """Map, lift and focus a new window after its initial layout is complete.

    A short topmost pulse is available for Windows where a newly mapped Toplevel
    can otherwise remain behind its owner.  The flag is always removed on idle.
    """

    window = resolve_window(owner)
    window.update_idletasks()
    if maximized:
        maximize_window(window)
    else:
        window.deiconify()
    window.lift()
    if temporary_topmost:
        window.attributes("-topmost", True)

        def release_topmost():
            try:
                if window.winfo_exists():
                    window.attributes("-topmost", False)
                    window.lift()
                    window.focus_force()
            except Exception:
                pass

        window.after_idle(release_topmost)
    else:
        window.focus_force()


def track_window_reference(registry: dict, key, owner) -> None:
    """Store a window owner and remove the same reference after destruction."""

    registry[key] = owner
    window = resolve_window(owner)

    def clear_destroyed(event):
        if event.widget is window and registry.get(key) is owner:
            registry.pop(key, None)

    window.bind("<Destroy>", clear_destroyed, add="+")


class DebouncedAction:
    """Schedule one Tk callback while cancelling an obsolete pending call."""

    def __init__(self, scheduler, delay_ms: int, callback: Callable[[], None]):
        self.scheduler = scheduler
        self.delay_ms = max(0, int(delay_ms))
        self.callback = callback
        self._after_id = None

    @property
    def pending(self) -> bool:
        return self._after_id is not None

    def schedule(self) -> None:
        self.cancel()
        self._after_id = self.scheduler.call_later(
            self.delay_ms,
            self._run,
        )

    def cancel(self) -> None:
        if self._after_id is None:
            return
        self.scheduler.cancel(self._after_id)
        self._after_id = None

    def _run(self) -> None:
        self._after_id = None
        self.callback()


class IntelligenceWindowSupport:
    """Own common Toplevel callbacks, close behaviour and Home notification."""

    def __init__(self, window, parent=None):
        self.window = window
        self.parent = parent
        self._after_ids: set[Any] = set()
        self._closed = False

    def install(self) -> None:
        # Keep new module windows hidden while their heavier layouts are built.
        # The shared presentation/maximise step reveals them only after their
        # final working-area geometry has been applied, preventing a visible
        # off-screen flash and repeated Windows redraws.
        try:
            self.window.withdraw()
        except Exception:
            pass
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Destroy>", self._on_destroy, add="+")

    def call_later(self, delay_ms: int, callback: Callable[[], None]):
        holder = {}

        def dispatch():
            callback_id = holder.get("id")
            if callback_id is not None:
                self._after_ids.discard(callback_id)
            if not self._closed:
                callback()

        callback_id = self.window.after(delay_ms, dispatch)
        holder["id"] = callback_id
        self._after_ids.add(callback_id)
        return callback_id

    def cancel(self, callback_id) -> None:
        self._after_ids.discard(callback_id)
        try:
            self.window.after_cancel(callback_id)
        except Exception:
            pass

    def cancel_all(self) -> None:
        for callback_id in tuple(self._after_ids):
            self.cancel(callback_id)

    def notify_dashboard(self, payload: Mapping[str, Any]) -> bool:
        callback = getattr(self.window, "dashboard_result_callback", None)
        if not callable(callback):
            return False
        callback(dict(payload))
        return True

    def notify_story_refresh(self, stories, publish_results, errors) -> bool:
        return self.notify_dashboard(
            {
                "stories": stories,
                "publish_results": publish_results,
                "errors": list(errors),
            }
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel_all()
        try:
            self.window.destroy()
        finally:
            self._restore_parent_focus()

    def _restore_parent_focus(self) -> None:
        try:
            if self.parent is None or not self.parent.winfo_exists():
                return
            self.parent.deiconify()
            self.parent.lift()
            self.parent.focus_force()
        except Exception:
            pass

    def _on_destroy(self, event) -> None:
        if event.widget is self.window:
            self._closed = True
            self.cancel_all()
