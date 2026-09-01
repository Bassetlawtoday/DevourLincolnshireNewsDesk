"""
Reusable statistics strip for Devour Lincolnshire NewsDesk modules.

This component displays a row of editorial statistics cards and provides
simple methods for updating their values at runtime.

Example:

    statistics = NewsDeskStatisticsStrip(
        parent,
        statistics=(
            ("immediate", "IMMEDIATE", "0", IMMEDIATE),
            ("urgent", "URGENT", "0", URGENT),
            ("routine", "ROUTINE", "0", ROUTINE),
            ("review", "STORY WORKSPACE", "0", ACCENT),
            ("total", "TOTAL STORIES", "0", SUCCESS),
        ),
    )

    statistics.grid(row=0, column=0, sticky="ew")
    statistics.set_value("total", 12)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Union

import customtkinter as ctk

from newsdesk.theme import APP_BG, BORDER, CARD_BG, TEXT_MUTED

StatisticValue = Union[str, int, float]


@dataclass(frozen=True)
class StatisticDefinition:
    """Configuration for a single statistics card."""

    key: str
    title: str
    value: StatisticValue
    colour: str


class NewsDeskStatisticsStrip(ctk.CTkFrame):
    """
    Shared statistics-card strip used by NewsDesk modules.

    Statistics may be supplied as ``StatisticDefinition`` objects or as
    four-item tuples in the following format:

        (key, title, initial_value, value_colour)
    """

    def __init__(
        self,
        master,
        *,
        statistics: Iterable[
            StatisticDefinition | tuple[str, str, StatisticValue, str]
        ],
        card_height: int = 82,
        horizontal_padding: int = 24,
        card_spacing: int = 6,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=APP_BG,
            corner_radius=0,
            **kwargs,
        )

        self.card_height = card_height
        self.horizontal_padding = horizontal_padding
        self.card_spacing = card_spacing

        self._definitions = self._normalise_statistics(statistics)

        if not self._definitions:
            raise ValueError(
                "NewsDeskStatisticsStrip requires at least one statistic."
            )

        self.value_labels: dict[str, ctk.CTkLabel] = {}
        self.cards: dict[str, ctk.CTkFrame] = {}

        self._build_cards()

    @staticmethod
    def _normalise_statistics(
        statistics: Iterable[
            StatisticDefinition | tuple[str, str, StatisticValue, str]
        ],
    ) -> tuple[StatisticDefinition, ...]:
        """Validate and normalise statistic definitions."""

        normalised: list[StatisticDefinition] = []
        seen_keys: set[str] = set()

        for item in statistics:
            if isinstance(item, StatisticDefinition):
                definition = item
            else:
                try:
                    key, title, value, colour = item
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Each statistic must contain key, title, value and colour."
                    ) from exc

                definition = StatisticDefinition(
                    key=str(key).strip(),
                    title=str(title).strip(),
                    value=value,
                    colour=str(colour).strip(),
                )

            if not definition.key:
                raise ValueError("Statistic keys cannot be empty.")

            if definition.key in seen_keys:
                raise ValueError(
                    f"Duplicate statistic key: {definition.key!r}"
                )

            seen_keys.add(definition.key)
            normalised.append(definition)

        return tuple(normalised)

    def _build_cards(self) -> None:
        """Create all statistics cards."""

        for column in range(len(self._definitions)):
            self.grid_columnconfigure(
                column,
                weight=1,
                uniform="newsdesk_statistics",
            )

        for column, definition in enumerate(self._definitions):
            card = ctk.CTkFrame(
                self,
                fg_color=CARD_BG,
                corner_radius=14,
                border_width=1,
                border_color=BORDER,
                height=self.card_height,
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=self._card_padding(column),
            )
            card.grid_propagate(False)

            title_label = ctk.CTkLabel(
                card,
                text=definition.title.upper(),
                font=("Arial", 11, "bold"),
                text_color=TEXT_MUTED,
            )
            title_label.pack(pady=(13, 3))

            value_label = ctk.CTkLabel(
                card,
                text=str(definition.value),
                font=("Arial", 25, "bold"),
                text_color=definition.colour,
            )
            value_label.pack(pady=(0, 13))

            self.cards[definition.key] = card
            self.value_labels[definition.key] = value_label

    def _card_padding(self, column: int) -> tuple[int, int]:
        """Return balanced horizontal padding for a card."""

        last_column = len(self._definitions) - 1

        left = (
            self.horizontal_padding
            if column == 0
            else self.card_spacing
        )
        right = (
            self.horizontal_padding
            if column == last_column
            else self.card_spacing
        )

        return left, right

    def set_value(self, key: str, value: StatisticValue) -> None:
        """Update one statistic value."""

        label = self._get_value_label(key)
        label.configure(text=str(value))

    def get_value(self, key: str) -> str:
        """Return the current displayed value for one statistic."""

        label = self._get_value_label(key)
        return str(label.cget("text"))

    def set_values(self, **values: StatisticValue) -> None:
        """Update several statistics in one call."""

        for key, value in values.items():
            self.set_value(key, value)

    def reset(self, value: StatisticValue = 0) -> None:
        """Reset every statistic to the supplied value."""

        for label in self.value_labels.values():
            label.configure(text=str(value))

    def set_colour(self, key: str, colour: str) -> None:
        """Change the display colour for one statistic value."""

        label = self._get_value_label(key)
        label.configure(text_color=colour)

    def has_statistic(self, key: str) -> bool:
        """Return whether a statistic key exists."""

        return key in self.value_labels

    def _get_value_label(self, key: str) -> ctk.CTkLabel:
        """Return a value label or raise a clear error."""

        try:
            return self.value_labels[key]
        except KeyError as exc:
            available = ", ".join(sorted(self.value_labels))
            raise KeyError(
                f"Unknown statistic key {key!r}. "
                f"Available keys: {available}"
            ) from exc