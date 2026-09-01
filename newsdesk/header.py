"""Compact reusable NewsDesk Pro header."""

from collections.abc import Sequence
from typing import Callable, Optional
import customtkinter as ctk
from PIL import Image
from newsdesk.theme import ACTION_BLUE, ACTION_BLUE_HOVER, BRAND_RED, BRAND_RED_HOVER, HEADER_BG, LOGO_PATH, TEXT_PRIMARY, TEXT_SECONDARY


class NewsDeskHeader(ctk.CTkFrame):
    def __init__(self, master, module_title: str, subtitle: str = "", primary_button_text: Optional[str] = None, primary_command: Optional[Callable] = None, close_command: Optional[Callable] = None, show_close_button: bool = True, secondary_actions: Sequence[tuple[str, Callable]] = (), badge_text: str = "", height: int = 122, **kwargs):
        super().__init__(master, fg_color=HEADER_BG, corner_radius=0, height=height, **kwargs)
        self.module_title, self.subtitle = module_title, subtitle
        self.grid_propagate(False); self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        brand = ctk.CTkFrame(self, fg_color="transparent"); brand.grid(row=0, column=0, padx=(22, 16), pady=14)
        if LOGO_PATH.exists():
            with Image.open(LOGO_PATH) as image: source = image.copy()
            self.brand_logo = ctk.CTkImage(light_image=source, dark_image=source, size=(88, 88)); ctk.CTkLabel(brand, text="", image=self.brand_logo).pack()
        title = ctk.CTkFrame(self, fg_color="transparent"); title.grid(row=0, column=1, sticky="w", pady=14)
        title_font = 22 if len(module_title) > 24 else 25
        self.title_label = ctk.CTkLabel(title, text=module_title.upper(), font=("Arial", title_font, "bold"), text_color=TEXT_PRIMARY, anchor="w")
        self.title_label.pack(anchor="w")
        if subtitle: ctk.CTkLabel(title, text=subtitle, font=("Arial", 13), text_color=TEXT_SECONDARY, anchor="w").pack(anchor="w", pady=(5, 0))
        controls = ctk.CTkFrame(self, fg_color="transparent"); controls.grid(row=0, column=2, sticky="e", padx=16, pady=16)
        self.primary_button = None
        if primary_button_text:
            self.primary_button = ctk.CTkButton(controls, text=primary_button_text, width=170, height=42, font=("Arial", 12, "bold"), fg_color=BRAND_RED, hover_color=BRAND_RED_HOVER, command=primary_command)
            self.primary_button.pack(side="left", padx=(0, 7))
        self.secondary_buttons = []
        for label, command in secondary_actions:
            button = ctk.CTkButton(controls, text=label, width=122, height=42, font=("Arial", 12, "bold"), fg_color=ACTION_BLUE, hover_color=ACTION_BLUE_HOVER, command=command)
            button.pack(side="left", padx=(0, 7)); self.secondary_buttons.append(button)
        self.badge = None
        self.close_button = None
        if show_close_button:
            self.close_button = ctk.CTkButton(controls, text="CLOSE", width=86, height=42, font=("Arial", 12, "bold"), fg_color="#475569", hover_color="#64748b", command=close_command)
            self.close_button.pack(side="left")

    def set_primary_button_state(self, state: str):
        if self.primary_button is not None: self.primary_button.configure(state=state)

    def set_primary_button_text(self, text: str):
        if self.primary_button is not None: self.primary_button.configure(text=text)

    def set_module_title(self, title: str):
        self.module_title = title; self.title_label.configure(text=title.upper())

    def set_status_hint(self, text: str): self.status_hint = text
