"""
Export utilities for Devour Lincolnshire NewsDesk.

Provides common export functions used throughout the application.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime


class Exporter:
    """Handles saving generated content."""

    @staticmethod
    def save_text(filename: str, text: str) -> Path:
        """
        Save plain text.

        Returns the saved path.
        """

        path = Path(filename)

        path.write_text(
            text,
            encoding="utf-8",
        )

        return path

    @staticmethod
    def save_html(filename: str, html: str) -> Path:
        """
        Save HTML.
        """

        return Exporter.save_text(filename, html)

    @staticmethod
    def save_markdown(filename: str, markdown: str) -> Path:
        """
        Save Markdown.
        """

        return Exporter.save_text(filename, markdown)

    @staticmethod
    def timestamp_filename(prefix: str, suffix: str = ".txt") -> str:
        """
        Generate a timestamped filename.

        Example:

            police_20260705_142233.txt
        """

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return f"{prefix}_{stamp}{suffix}"