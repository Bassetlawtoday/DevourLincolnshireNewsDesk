from __future__ import annotations

from collections.abc import Iterable

from services.roadworks_models import RoadworkRecord
from services.roadworks.nottinghamshire_cc import (
    NottinghamshireCountyCouncilSource,
)
from services.roadworks.via_source import ViaSource


class RoadworksScraper:
    """
    Coordinates roadworks and travel data sources.

    Individual live sources are kept in separate source classes. Every source
    must return normalised RoadworkRecord objects.
    """

    def __init__(self):
        self.records: list[RoadworkRecord] = []
        self.sources = [
            NottinghamshireCountyCouncilSource(),
            ViaSource(),
        ]

    def scrape(self) -> list[RoadworkRecord]:
        """Collect records from every enabled Roadworks source."""

        self.records.clear()

        for source in self.sources:
            self._collect_from_source(source)

        return list(self.records)

    def diagnostics(self) -> dict:
        results = {}

        for source in self.sources:
            diag = getattr(source, "diagnostics", None)

            if callable(diag):
                try:
                    results[source.name] = diag()
                except Exception as exc:
                    results[source.name] = {"error": str(exc)}

        return results

    def _collect_from_source(self, source) -> None:
        try:
            records = source.fetch()
        except Exception as exc:
            print(f"{source.name}: {exc}")
            return

        self._add_records(records)

    def _add_records(self, records: Iterable[RoadworkRecord] | None) -> None:
        if records is None:
            return

        for record in records:
            self.add_record(record)

    def add_record(self, record: RoadworkRecord) -> None:
        if not isinstance(record, RoadworkRecord):
            raise TypeError(
                "RoadworksScraper.add_record expects a RoadworkRecord."
            )

        self.records.append(record)

    def close(self) -> None:
        for source in self.sources:
            close = getattr(source, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass