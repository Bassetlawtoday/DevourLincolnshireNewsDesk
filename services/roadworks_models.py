from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class RoadworkRecord:
    """
    A normalised roadworks or travel-disruption record.

    Every source scraper should convert its data into this structure before
    records are scored, stored or displayed.
    """

    record_id: str = ""
    title: str = ""

    road: str = ""
    location: str = ""
    town: str = ""

    description: str = ""
    traffic_management: str = ""
    status: str = ""

    start_date: str = ""
    end_date: str = ""

    promoter: str = ""
    authority: str = ""

    source: str = ""
    source_url: str = ""

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    category: str = "Roadworks"
    severity: str = "Low"
    score: int = 0

    is_emergency: bool = False
    is_road_closed: bool = False
    is_overnight: bool = False

    def searchable_text(self) -> str:
        """
        Return the main text fields as one lower-case searchable string.
        """
        values = (
            self.title,
            self.road,
            self.location,
            self.town,
            self.description,
            self.traffic_management,
            self.status,
            self.promoter,
            self.authority,
            self.category,
        )

        return " ".join(
            str(value).strip()
            for value in values
            if value
        ).lower()

    def unique_key(self) -> str:
        """
        Return a stable key suitable for duplicate detection.
        """
        if self.record_id:
            return f"{self.source}|{self.record_id}".lower()

        return "|".join(
            (
                self.source,
                self.road,
                self.location,
                self.start_date,
                self.end_date,
            )
        ).lower()

    def to_dict(self) -> dict:
        """
        Convert the complete record into a dictionary.
        """
        return asdict(self)
