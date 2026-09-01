"""
Official club source scrapers available to SportDesk.
"""

from __future__ import annotations

from newsdesk.sports.clubs.alfreton_town import AlfretonTownScraper
from newsdesk.sports.clubs.boston_united import BostonUnitedScraper
from newsdesk.sports.clubs.doncaster_rovers import DoncasterRoversScraper
from newsdesk.sports.clubs.gainsborough_trinity import GainsboroughTrinityScraper
from newsdesk.sports.clubs.harworth_colliery import HarworthCollieryScraper
from newsdesk.sports.clubs.lincoln_city import LincolnCityScraper
from newsdesk.sports.clubs.lincoln_united import LincolnUnitedScraper
from newsdesk.sports.clubs.mansfield_town import MansfieldTownScraper
from newsdesk.sports.clubs.nottingham_forest import NottinghamForestScraper
from newsdesk.sports.clubs.notts_county import NottsCountyScraper
from newsdesk.sports.clubs.retford_fc import RetfordFCScraper
from newsdesk.sports.clubs.retford_united import RetfordUnitedScraper
from newsdesk.sports.clubs.scunthorpe_united import ScunthorpeUnitedScraper
from newsdesk.sports.clubs.sheffield_united import SheffieldUnitedScraper
from newsdesk.sports.clubs.sheffield_wednesday import SheffieldWednesdayScraper
from newsdesk.sports.clubs.sjr_worksop import SJRWorksopScraper
from newsdesk.sports.clubs.worksop_town import WorksopTownScraper


def default_club_scrapers() -> list[object]:
    """Create fresh instances of all configured official club scrapers."""

    return [
        RetfordFCScraper(),
        SJRWorksopScraper(),
        LincolnCityScraper(),
        LincolnUnitedScraper(),
        GainsboroughTrinityScraper(),
        AlfretonTownScraper(),
        BostonUnitedScraper(),
        ScunthorpeUnitedScraper(),
    ]


__all__ = [
    "AlfretonTownScraper",
    "BostonUnitedScraper",
    "DoncasterRoversScraper",
    "GainsboroughTrinityScraper",
    "HarworthCollieryScraper",
    "LincolnCityScraper",
    "LincolnUnitedScraper",
    "MansfieldTownScraper",
    "NottinghamForestScraper",
    "NottsCountyScraper",
    "RetfordFCScraper",
    "RetfordUnitedScraper",
    "ScunthorpeUnitedScraper",
    "SheffieldUnitedScraper",
    "SheffieldWednesdayScraper",
    "SJRWorksopScraper",
    "WorksopTownScraper",
    "default_club_scrapers",
]
