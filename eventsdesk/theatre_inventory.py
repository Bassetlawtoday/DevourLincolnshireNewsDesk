from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TheatrePlatform:
    name: str
    website: str
    area: str
    platform: str
    evidence: str
    client_name: str | None = None
    ticket_host: str | None = None


# Confirmed platform membership is deliberately separated from client_name.
# A client name is only filled once a public API endpoint has been validated.
THEATRE_PLATFORMS: tuple[TheatrePlatform, ...] = (
    TheatrePlatform("Nottingham Playhouse", "https://www.nottinghamplayhouse.co.uk/", "Nottingham", "Spektrix", "Spektrix case study", ticket_host="tickets.nottinghamplayhouse.co.uk"),
    TheatrePlatform("Derby Theatre", "https://www.derbytheatre.co.uk/", "Derby", "Spektrix", "Spektrix founder-member history", ticket_host="tickets.derbytheatre.co.uk"),
    TheatrePlatform("Mansfield Palace Theatre", "https://www.mansfield.gov.uk/palacetheatre", "Mansfield", "Spektrix", "venue announcement and Spektrix case study"),
    TheatrePlatform("Birmingham Rep", "https://www.birmingham-rep.co.uk/", "Birmingham", "Spektrix", "first-party account/booking pages identify Spektrix"),
    TheatrePlatform("Warwick Arts Centre", "https://www.warwickartscentre.co.uk/", "Coventry / Warwickshire", "Spektrix", "first-party accessibility and cookie policies identify Spektrix", ticket_host="tickets.warwickartscentre.co.uk"),
    TheatrePlatform("Theatre Severn", "https://www.theatresevern.co.uk/", "Shrewsbury", "Spektrix", "first-party cookie/privacy policies identify Spektrix", ticket_host="tickets.theatresevern.co.uk"),
    TheatrePlatform("Buxton Opera House", "https://buxtonoperahouse.org.uk/", "Buxton", "Spektrix", "current venue recruitment material identifies Spektrix", ticket_host="bookings.buxtonoperahouse.org.uk"),
    TheatrePlatform("New Vic Theatre", "https://www.newvictheatre.org.uk/", "Newcastle-under-Lyme", "Spektrix", "venue recruitment material identifies Spektrix", ticket_host="tickets.newvictheatre.org.uk"),
    TheatrePlatform("MAC Birmingham", "https://macbirmingham.co.uk/", "Birmingham", "Spektrix candidate", "ticket host strongly associated with Spektrix; validate at runtime", ticket_host="tickets.macbirmingham.co.uk"),
    TheatrePlatform("Curve Leicester", "https://www.curveonline.co.uk/", "Leicester", "Spektrix candidate", "booking host strongly associated with Spektrix; validate at runtime", ticket_host="bookings.curveonline.co.uk"),
    TheatrePlatform("Tamworth Assembly Rooms", "https://www.tamworthassemblyrooms.co.uk/", "Tamworth", "Spektrix candidate", "ticket host strongly associated with Spektrix; validate at runtime", ticket_host="tickets.tamworthassemblyrooms.co.uk"),
    TheatrePlatform("Lincoln Arts Centre", "https://lincolnartscentre.co.uk/", "Lincoln", "Spektrix", "first-party privacy policy confirms Spektrix online ticketing"),
    TheatrePlatform("Lichfield Garrick", "https://www.lichfieldgarrick.com/", "Lichfield", "Spektrix", "public listings are sourced from participating Spektrix venue box offices"),
)


def confirmed_spektrix_theatres() -> list[TheatrePlatform]:
    return [x for x in THEATRE_PLATFORMS if x.platform == "Spektrix"]
