"""
Reusable base window for all Devour Lincolnshire NewsDesk modules.

Every NewsDesk module should inherit from NewsDeskWindow rather than
directly from CTkToplevel.

Example:

    class PoliceWindow(NewsDeskWindow):

        def __init__(self, master):

            super().__init__(
                master,
                module_title="Police Intelligence",
                subtitle="Collect • Classify • Review • Publish",
                primary_button_text="REFRESH POLICE NEWS",
                primary_command=self.refresh_stories,
            )

            ...
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from newsdesk.header import NewsDeskHeader
from newsdesk.theme import (
    APP_BG,
    APP_NAME,
    HEADER_BG,
    TEXT_MUTED,
    TEXT_PRIMARY,
    VERSION,
)


class NewsDeskWindow(ctk.CTkToplevel):
    """
    Base window used by every NewsDesk module.

    Automatically provides:

    • standard sizing
    • branding
    • reusable header
    • content workspace
    • status bar
    • common helper methods
    """

    DEFAULT_WIDTH = 1500
    DEFAULT_HEIGHT = 900

    def __init__(
        self,
        master,
        *,
        module_title: str,
        subtitle: str = "",
        primary_button_text: Optional[str] = None,
        primary_command: Optional[Callable] = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        show_close_button: bool = True,
    ):

        super().__init__(master)

        self.withdraw()

        self.module_title = module_title

        self.title(f"{APP_NAME} — {module_title}")

        self.geometry(f"{width}x{height}")

        self.minsize(1200, 700)

        self.configure(fg_color=APP_BG)

        self.protocol("WM_DELETE_WINDOW", self.close)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # -------------------------------------------------------
        # Header
        # -------------------------------------------------------

        self.header = NewsDeskHeader(
            self,
            module_title=module_title,
            subtitle=subtitle,
            primary_button_text=primary_button_text,
            primary_command=primary_command,
            close_command=self.close,
            show_close_button=show_close_button,
        )

        self.header.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        # -------------------------------------------------------
        # Workspace
        # -------------------------------------------------------

        self.workspace = ctk.CTkFrame(
            self,
            fg_color=APP_BG,
            corner_radius=0,
        )

        self.workspace.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=1)

        # -------------------------------------------------------
        # Status Bar
        # -------------------------------------------------------

        self.status_bar = ctk.CTkFrame(
            self,
            fg_color=HEADER_BG,
            height=34,
            corner_radius=0,
        )

        self.status_bar.grid(
            row=2,
            column=0,
            sticky="ew",
        )

        self.status_bar.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text=f"{module_title} ready",
            font=("Arial", 11),
            text_color=TEXT_MUTED,
            anchor="w",
        )

        self.status_label.grid(
            row=0,
            column=0,
            padx=18,
            pady=7,
            sticky="w",
        )

        self.version_label = ctk.CTkLabel(
            self.status_bar,
            text=f"{APP_NAME}  {VERSION}",
            font=("Arial", 10),
            text_color=TEXT_MUTED,
        )

        self.version_label.grid(
            row=0,
            column=1,
            padx=18,
            pady=7,
            sticky="e",
        )

        self.deiconify()

        self.after(10, self.focus_force)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_status(self, text: str):
        """
        Update the status bar text.
        """

        self.status_label.configure(text=text)

    def clear_status(self):
        """
        Reset status text.
        """

        self.status_label.configure(
            text=f"{self.module_title} ready"
        )

    def enable_primary_button(self):
        """
        Enable the header's primary button.
        """

        self.header.set_primary_button_state("normal")

    def disable_primary_button(self):
        """
        Disable the header's primary button.
        """

        self.header.set_primary_button_state("disabled")

    def set_primary_button_text(self, text: str):
        """
        Change the header button label.
        """

        self.header.set_primary_button_text(text)

    # ------------------------------------------------------------------
    # Hooks for derived windows
    # ------------------------------------------------------------------

    def on_show(self):
        """
        Override in child classes if required.

        Called after the window becomes visible.
        """

    def on_close(self):
        """
        Override in child classes.

        Use for cleanup.
        """

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------

    def close(self):
        """
        Safely close the window.
        """

        try:
            self.on_close()
        finally:
            self.destroy()