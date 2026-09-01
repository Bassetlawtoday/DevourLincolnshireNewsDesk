from abc import ABC, abstractmethod

from services.roadworks_models import RoadworkRecord


class BaseRoadworksSource(ABC):
    """
    Base class for every Roadworks source.

    Every concrete source returns RoadworkRecord objects.
    """

    name = "Unnamed Source"

    @abstractmethod
    def fetch(self) -> list[RoadworkRecord]:
        """
        Return RoadworkRecord objects.
        """
        raise NotImplementedError
