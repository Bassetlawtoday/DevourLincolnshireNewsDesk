"""Editable Story Desk window for generated planning copy."""

import customtkinter as ctk

from editorial.story_generator import generate_story


APP_BG = ("#eef2f6", "#101820")
PANEL_BG = ("#ffffff", "#17232d")
CARD_BG = ("#f7f9fc", "#1f2d38")
TEXT = ("#16202a", "#f2f6f8")
MUTED_TEXT = ("#5b6874", "#b7c3cc")
BORDER = ("#d6dee6", "#334754")
PRIMARY = "#1769aa"
PRIMARY_DARK = "#0f4f83"


class StoryDeskWindow:
    """Display and edit generated story formats."""

    def __init__(self, parent, story):
        self.story = story or {}
        self.generated = generate_story(self.story)

        self.window = ctk.CTkToplevel(parent)
        self.window.title("Story Desk")
        self.window.geometry("1100x860")
        self.window.minsize(900, 700)
        self.window.configure(fg_color=APP_BG)

        self.window.transient(parent)
        self.window.lift()
        self.window.focus_force()

        self.build()

    def build(self):
        self._build_header()

        content = ctk.CTkScrollableFrame(
            self.window,
            fg_color=APP_BG,
            corner_radius=0,
        )
        content.pack(fill="both", expand=True, padx=18, pady=(14, 12))

        self.headline_box = self._build_editor_section(
            content,
            title="Headline",
            text=self.generated.get("headline", ""),
            height=90,
        )

        self.website_box = self._build_editor_section(
            content,
            title="Website Article",
            text=self.generated.get("website_article", ""),
            height=300,
        )

        self.facebook_box = self._build_editor_section(
            content,
            title="Facebook Post",
            text=self.generated.get("facebook_post", ""),
            height=240,
        )

        self.newsletter_box = self._build_editor_section(
            content,
            title="Newsletter Copy",
            text=self.generated.get("newsletter_copy", ""),
            height=180,
        )

        self._build_footer()

    def _build_header(self):
        header = ctk.CTkFrame(
            self.window,
            fg_color=PANEL_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        header.pack(fill="x")

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=28, pady=18)

        title_block = ctk.CTkFrame(inner, fg_color="transparent")
        title_block.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            title_block,
            text="DEVOUR LINCOLNSHIRE NEWSDESK",
            font=("Arial", 13, "bold"),
            text_color=PRIMARY,
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            title_block,
            text="Story Desk",
            font=("Arial", 29, "bold"),
            text_color=TEXT,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        reference = self.story.get("reference") or "No reference"
        area = self.story.get("area") or "Unknown area"

        ctk.CTkLabel(
            title_block,
            text=f"{area}  •  {reference}",
            font=("Arial", 12),
            text_color=MUTED_TEXT,
            anchor="w",
        ).pack(fill="x", pady=(3, 0))

        ctk.CTkLabel(
            inner,
            text="VERSION 2.3",
            font=("Arial", 12, "bold"),
            text_color="#ffffff",
            fg_color=PRIMARY,
            corner_radius=10,
            padx=14,
            pady=7,
        ).pack(side="right", padx=(18, 0))

    def _build_editor_section(self, parent, title, text, height):
        panel = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        panel.pack(fill="x", pady=(0, 16))

        heading = ctk.CTkFrame(panel, fg_color="transparent")
        heading.pack(fill="x", padx=18, pady=(14, 8))

        ctk.CTkLabel(
            heading,
            text=title,
            font=("Arial", 18, "bold"),
            text_color=TEXT,
        ).pack(side="left")

        textbox = ctk.CTkTextbox(
            panel,
            height=height,
            font=("Arial", 13),
            wrap="word",
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER,
        )
        textbox.pack(fill="x", padx=18, pady=(0, 10))
        textbox.insert("1.0", text)

        button_row = ctk.CTkFrame(panel, fg_color="transparent")
        button_row.pack(fill="x", padx=18, pady=(0, 14))

        ctk.CTkButton(
            button_row,
            text=f"Copy {title}",
            width=150,
            height=34,
            fg_color=PRIMARY,
            hover_color=PRIMARY_DARK,
            command=lambda box=textbox, label=title: self.copy_text(
                box,
                label,
            ),
        ).pack(side="left")

        return textbox

    def copy_text(self, textbox, label):
        text = textbox.get("1.0", "end").strip()

        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()

        self.status.configure(text=f"{label} copied to clipboard")

    def copy_all(self):
        headline = self.headline_box.get("1.0", "end").strip()
        website = self.website_box.get("1.0", "end").strip()
        facebook = self.facebook_box.get("1.0", "end").strip()
        newsletter = self.newsletter_box.get("1.0", "end").strip()

        combined = (
            f"HEADLINE\n{headline}\n\n"
            f"WEBSITE ARTICLE\n{website}\n\n"
            f"FACEBOOK POST\n{facebook}\n\n"
            f"NEWSLETTER COPY\n{newsletter}"
        )

        self.window.clipboard_clear()
        self.window.clipboard_append(combined)
        self.window.update()

        self.status.configure(text="All story formats copied to clipboard")

    def _build_footer(self):
        footer = ctk.CTkFrame(
            self.window,
            fg_color=PANEL_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        footer.pack(fill="x")

        inner = ctk.CTkFrame(footer, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=12)

        self.status = ctk.CTkLabel(
            inner,
            text="Story draft ready",
            font=("Arial", 11),
            text_color=MUTED_TEXT,
        )
        self.status.pack(side="left")

        ctk.CTkButton(
            inner,
            text="Copy All",
            width=130,
            height=36,
            fg_color=PRIMARY,
            hover_color=PRIMARY_DARK,
            command=self.copy_all,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            inner,
            text="Close",
            width=110,
            height=36,
            fg_color="#66737d",
            hover_color="#4f5a62",
            command=self.window.destroy,
        ).pack(side="right")


def open_story_desk(parent, story):
    """Open the Story Desk for one selected story."""
    return StoryDeskWindow(parent, story)