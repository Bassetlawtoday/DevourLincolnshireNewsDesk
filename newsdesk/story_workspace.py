"""
Reusable story workspace for NewsDesk modules.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from newsdesk.theme import BORDER, HEADER_BG, PANEL_BG, TEXT_MUTED, TEXT_PRIMARY


class NewsDeskStoryWorkspace(ctk.CTkFrame):
    """Shared editorial workspace panel."""

    def __init__(
        self,
        master,
        *,
        title: str = "STORY WORKSPACE",
        empty_heading: str = "SELECT A STORY",
        empty_message: str = (
            "Choose a story from the queue to view its summary,\n"
            "classification, priority score and editorial decision."
        ),
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=HEADER_BG,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
            **kwargs,
        )

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._title = title
        self._empty_heading = empty_heading
        self._empty_message = empty_message

        self._build()

    def _build(self):
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=22, pady=(17, 10))

        ctk.CTkLabel(
            heading,
            text=self._title,
            font=("Arial", 16, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self.selection_status = ctk.CTkLabel(
            heading,
            text="NO STORY SELECTED",
            font=("Arial", 11, "bold"),
            text_color=TEXT_MUTED,
        )
        self.selection_status.pack(side="right")

        self.content = ctk.CTkScrollableFrame(
            self,
            fg_color=PANEL_BG,
            corner_radius=12,
        )
        self.content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(0, 12),
        )

        self.show_placeholder()

    def clear(self):
        for w in self.content.winfo_children():
            w.destroy()

    def show_placeholder(self):
        self.clear()
        frame = ctk.CTkFrame(self.content, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=40, pady=90)

        ctk.CTkLabel(
            frame,
            text=self._empty_heading,
            font=("Arial", 21, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            frame,
            text=self._empty_message,
            font=("Arial", 13),
            text_color=TEXT_MUTED,
            justify="center",
        ).pack()

    def set_story(self, title: str, body: str, status: Optional[str] = None):
        self.clear()

        if status:
            self.selection_status.configure(text=status)
        else:
            self.selection_status.configure(text="STORY SELECTED")

        ctk.CTkLabel(
            self.content,
            text=title,
            font=("Arial", 22, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=20, pady=(20, 10))

        textbox = ctk.CTkTextbox(self.content, wrap="word")
        textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        textbox.insert("1.0", body)
        textbox.configure(state="disabled")

    def set_status(self, text: str):
        self.selection_status.configure(text=text)