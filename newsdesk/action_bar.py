"""
Reusable publishing action bar for Devour Lincolnshire NewsDesk modules.

The component centralises the standard Website, Facebook, Social and Open
Source controls used by intelligence windows while keeping the buttons
available through the public ``buttons`` mapping for backwards compatibility.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Final

import customtkinter as ctk

from newsdesk.theme import TEXT_PRIMARY


ActionCommand = Callable[[str], None]


class NewsDeskActionBar(ctk.CTkFrame):
    """Shared row of publishing action buttons."""

    DEFAULT_ACTIONS: Final[tuple[str, ...]] = (
        "WEBSITE ARTICLE",
        "FACEBOOK POST",
        "ADD TO SOCIALS",
        "OPEN SOURCE",
    )

    def __init__(
        self,
        master,
        *,
        actions: Iterable[str] = DEFAULT_ACTIONS,
        command: ActionCommand | None = None,
        initially_enabled: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.command = command
        self.buttons: dict[str, ctk.CTkButton] = {}

        normalised_actions = self._normalise_actions(actions)
        initial_state = "normal" if initially_enabled else "disabled"

        for column, action in enumerate(normalised_actions):
            self.grid_columnconfigure(column, weight=1)

            button = ctk.CTkButton(
                self,
                text=action,
                height=38,
                corner_radius=10,
                font=("Arial", 11, "bold"),
                fg_color="#374151",
                hover_color="#475569",
                text_color=TEXT_PRIMARY,
                state=initial_state,
                command=lambda selected_action=action: self._clicked(
                    selected_action
                ),
            )
            button.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=5,
            )

            self.buttons[action] = button

    @staticmethod
    def _normalise_actions(actions: Iterable[str]) -> tuple[str, ...]:
        """Validate actions and remove accidental duplicates."""

        normalised: list[str] = []
        seen: set[str] = set()

        for value in actions:
            action = str(value).strip()

            if not action:
                raise ValueError(
                    "NewsDeskActionBar actions must contain non-empty names."
                )

            if action in seen:
                continue

            seen.add(action)
            normalised.append(action)

        if not normalised:
            raise ValueError(
                "NewsDeskActionBar requires at least one action."
            )

        return tuple(normalised)

    def _clicked(self, action: str) -> None:
        """Forward a button click to the configured module callback."""

        if self.command is not None:
            self.command(action)

    def set_command(self, command: ActionCommand | None) -> None:
        """Replace or clear the callback used for future button clicks."""

        self.command = command

    def enable_all(self) -> None:
        """Enable every action button."""

        self.set_all_enabled(True)

    def disable_all(self) -> None:
        """Disable every action button."""

        self.set_all_enabled(False)

    def set_all_enabled(self, enabled: bool) -> None:
        """Set all action buttons to the same enabled state."""

        state = "normal" if enabled else "disabled"

        for button in self.buttons.values():
            button.configure(state=state)

    def enable(self, action: str) -> None:
        """Enable one named action."""

        self._button(action).configure(state="normal")

    def disable(self, action: str) -> None:
        """Disable one named action."""

        self._button(action).configure(state="disabled")

    def set_enabled(self, action: str, enabled: bool) -> None:
        """Set one named action to an enabled or disabled state."""

        self._button(action).configure(
            state="normal" if enabled else "disabled"
        )

    def set_text(self, action: str, text: str) -> None:
        """
        Change the visible label while retaining the original action key.

        The callback continues to receive ``action`` so changing display text
        cannot break a module's publishing dispatch logic.
        """

        label = str(text).strip()

        if not label:
            raise ValueError("Action button text cannot be empty.")

        self._button(action).configure(text=label)

    def button(self, action: str) -> ctk.CTkButton:
        """Return one action button for compatibility or custom styling."""

        return self._button(action)

    def _button(self, action: str) -> ctk.CTkButton:
        try:
            return self.buttons[action]
        except KeyError as error:
            available = ", ".join(self.buttons)
            raise KeyError(
                f"Unknown NewsDesk action {action!r}. "
                f"Available actions: {available}."
            ) from error
