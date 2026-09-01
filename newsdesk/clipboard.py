"""
Shared clipboard utilities for Devour Lincolnshire NewsDesk.
"""

from __future__ import annotations

import tkinter as tk


class ClipboardManager:
    """
    Central clipboard helper used throughout NewsDesk.

    Example:

        ClipboardManager.copy(root, article)

        ClipboardManager.copy(root, facebook_post)

    """

    @staticmethod
    def copy(widget, text: str) -> None:
        """Copy text to the Windows clipboard."""

        if text is None:
            text = ""

        widget.clipboard_clear()
        widget.clipboard_append(str(text))
        widget.update()

    @staticmethod
    def paste(widget) -> str:
        """Return clipboard contents."""

        try:
            return widget.clipboard_get()

        except tk.TclError:
            return ""

    @staticmethod
    def has_text(widget) -> bool:
        """True if clipboard contains text."""

        return ClipboardManager.paste(widget) != ""

    @staticmethod
    def clear(widget) -> None:
        """Empty clipboard."""

        widget.clipboard_clear()
        widget.update()