"""
Shared collection progress models.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class CollectionProgress:
    """
    Represents the current progress of a collection task.
    """

    current: int = 0
    total: int = 0
    message: str = ""

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return (self.current / self.total) * 100.0

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.current >= self.total

    def update(
        self,
        current: int,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        self.current = current

        if total is not None:
            self.total = total

        if message is not None:
            self.message = message
