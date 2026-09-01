from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CouncilEventSource:
    name: str
    events_url: str
    area: str
    source_type: str = "Council / community"
    discovery_mode: str = "platform-and-endpoint"


# All 67 council/public-sector sources in the Midlands source map.
# A homepage URL means discovery should first locate the dedicated events page.
COUNCIL_EVENT_SOURCES: tuple[CouncilEventSource, ...] = (
    CouncilEventSource('Nottinghamshire County Council Events', 'https://www.nottinghamshire.gov.uk/events', 'Nottinghamshire', 'Council calendar'),
    CouncilEventSource('Nottingham City Council Events', 'https://www.nottinghamcity.gov.uk/events/', 'Nottingham', 'Council calendar'),
    CouncilEventSource('Newark & Sherwood District Council', 'https://www.newark-sherwooddc.gov.uk/events/', 'Newark & Sherwood', 'Council calendar'),
    CouncilEventSource('Bassetlaw District Council', 'https://www.bassetlaw.gov.uk/', 'Bassetlaw', 'Council / community'),
    CouncilEventSource('Mansfield District Council', 'https://www.mansfield.gov.uk/events', 'Mansfield', 'Council calendar'),
    CouncilEventSource('Ashfield District Council', 'https://www.ashfield.gov.uk/', 'Ashfield', 'Council / community'),
    CouncilEventSource('Gedling Borough Council', 'https://www.gedling.gov.uk/', 'Gedling', 'Council / community'),
    CouncilEventSource('Broxtowe Borough Council', 'https://www.broxtowe.gov.uk/', 'Broxtowe', 'Council / community'),
    CouncilEventSource('Rushcliffe Borough Council', 'https://www.rushcliffe.gov.uk/', 'Rushcliffe', 'Council / community'),
    CouncilEventSource('Derbyshire County Council Events', 'https://www.derbyshire.gov.uk/leisure/events/our-events.aspx', 'Derbyshire', 'Council calendar'),
    CouncilEventSource('Derby City Council', 'https://www.derby.gov.uk/', 'Derby', 'Council / community'),
    CouncilEventSource('Derby LIVE', 'https://www.derbylive.co.uk/', 'Derby', 'Council entertainment'),
    CouncilEventSource('Chesterfield Borough Council', 'https://www.chesterfield.gov.uk/', 'Chesterfield', 'Council / community'),
    CouncilEventSource('Amber Valley Borough Council', 'https://www.ambervalley.gov.uk/', 'Amber Valley', 'Council / community'),
    CouncilEventSource('High Peak Borough Council', 'https://www.highpeak.gov.uk/', 'High Peak', 'Council / community'),
    CouncilEventSource('Derbyshire Dales District Council', 'https://www.derbyshiredales.gov.uk/', 'Derbyshire Dales', 'Council / community'),
    CouncilEventSource('Erewash Borough Council', 'https://www.erewash.gov.uk/', 'Erewash', 'Council / community'),
    CouncilEventSource('North East Derbyshire District Council', 'https://www.ne-derbyshire.gov.uk/', 'North East Derbyshire', 'Council / community'),
    CouncilEventSource('Bolsover District Council', 'https://www.bolsover.gov.uk/', 'Bolsover', 'Council / community'),
    CouncilEventSource('Leicestershire County Council Whats On', 'https://www.leicestershire.gov.uk/whats-on', 'Leicestershire', 'Council calendar'),
    CouncilEventSource('Leicester City Council', 'https://www.leicester.gov.uk/', 'Leicester', 'Council / community'),
    CouncilEventSource('Charnwood Borough Council', 'https://www.charnwood.gov.uk/', 'Charnwood', 'Council / community'),
    CouncilEventSource('Harborough District Council', 'https://www.harborough.gov.uk/', 'Harborough', 'Council / community'),
    CouncilEventSource('Hinckley & Bosworth Borough Council', 'https://www.hinckley-bosworth.gov.uk/', 'Hinckley & Bosworth', 'Council / community'),
    CouncilEventSource('Melton Borough Council', 'https://www.melton.gov.uk/', 'Melton', 'Council / community'),
    CouncilEventSource('North West Leicestershire District Council', 'https://www.nwleics.gov.uk/', 'North West Leicestershire', 'Council / community'),
    CouncilEventSource('Blaby District Council', 'https://www.blaby.gov.uk/', 'Blaby', 'Council / community'),
    CouncilEventSource('Oadby & Wigston Borough Council', 'https://www.oadby-wigston.gov.uk/', 'Oadby & Wigston', 'Council / community'),
    CouncilEventSource('Lincolnshire County Council', 'https://www.lincolnshire.gov.uk/', 'Lincolnshire', 'Council / community'),
    CouncilEventSource('City of Lincoln Council', 'https://www.lincoln.gov.uk/', 'Lincoln', 'Council / community'),
    CouncilEventSource('South Kesteven District Council', 'https://www.southkesteven.gov.uk/', 'South Kesteven', 'Council / community'),
    CouncilEventSource('North Kesteven District Council', 'https://www.n-kesteven.gov.uk/', 'North Kesteven', 'Council / community'),
    CouncilEventSource('East Lindsey District Council', 'https://www.e-lindsey.gov.uk/', 'East Lindsey', 'Council / community'),
    CouncilEventSource('West Lindsey District Council', 'https://www.west-lindsey.gov.uk/', 'West Lindsey', 'Council / community'),
    CouncilEventSource('Boston Borough Council', 'https://www.boston.gov.uk/', 'Boston', 'Council / community'),
    CouncilEventSource('South Holland District Council', 'https://www.sholland.gov.uk/', 'South Holland', 'Council / community'),
    CouncilEventSource('West Northamptonshire Council', 'https://www.westnorthants.gov.uk/', 'West Northamptonshire', 'Council / community'),
    CouncilEventSource('North Northamptonshire Council', 'https://www.northnorthants.gov.uk/', 'North Northamptonshire', 'Council / community'),
    CouncilEventSource('Northampton Town Council', 'https://www.northamptontowncouncil.gov.uk/', 'Northampton', 'Town council'),
    CouncilEventSource('Dudley Council', 'https://www.dudley.gov.uk/', 'Dudley', 'Council / community'),
    CouncilEventSource('Walsall Council', 'https://go.walsall.gov.uk/', 'Walsall', 'Council / community'),
    CouncilEventSource('Wolverhampton Council', 'https://www.wolverhampton.gov.uk/', 'Wolverhampton', 'Council / community'),
    CouncilEventSource('Solihull Metropolitan Borough Council', 'https://www.solihull.gov.uk/', 'Solihull', 'Council / community'),
    CouncilEventSource('Coventry City Council', 'https://www.coventry.gov.uk/', 'Coventry', 'Council / community'),
    CouncilEventSource('Warwickshire County Council', 'https://www.warwickshire.gov.uk/', 'Warwickshire', 'Council / community'),
    CouncilEventSource('Warwick District Council', 'https://www.warwickdc.gov.uk/', 'Warwick District', 'Council / community'),
    CouncilEventSource('Stratford-on-Avon District Council', 'https://www.stratford.gov.uk/', 'Stratford District', 'Council / community'),
    CouncilEventSource('Rugby Borough Council', 'https://www.rugby.gov.uk/', 'Rugby', 'Council / community'),
    CouncilEventSource('Staffordshire County Council', 'https://www.staffordshire.gov.uk/', 'Staffordshire', 'Council / community'),
    CouncilEventSource('Stoke-on-Trent City Council', 'https://www.stoke.gov.uk/', 'Stoke-on-Trent', 'Council / community'),
    CouncilEventSource('Cannock Chase District Council', 'https://www.cannockchasedc.gov.uk/', 'Cannock Chase', 'Council / community'),
    CouncilEventSource('East Staffordshire Borough Council', 'https://www.eaststaffsbc.gov.uk/', 'East Staffordshire', 'Council / community'),
    CouncilEventSource('Lichfield District Council', 'https://www.lichfielddc.gov.uk/', 'Lichfield', 'Council / community'),
    CouncilEventSource('Newcastle-under-Lyme Borough Council', 'https://www.newcastle-staffs.gov.uk/', 'Newcastle-under-Lyme', 'Council / community'),
    CouncilEventSource('Stafford Borough Council', 'https://www.staffordbc.gov.uk/', 'Stafford', 'Council / community'),
    CouncilEventSource('Staffordshire Moorlands District Council', 'https://www.staffsmoorlands.gov.uk/', 'Staffordshire Moorlands', 'Council / community'),
    CouncilEventSource('Tamworth Borough Council', 'https://www.tamworth.gov.uk/', 'Tamworth', 'Council / community'),
    CouncilEventSource('Worcestershire County Council', 'https://www.worcestershire.gov.uk/', 'Worcestershire', 'Council / community'),
    CouncilEventSource('Worcester City Council', 'https://www.worcester.gov.uk/', 'Worcester', 'Council / community'),
    CouncilEventSource('Wyre Forest District Council', 'https://www.wyreforestdc.gov.uk/', 'Wyre Forest', 'Council / community'),
    CouncilEventSource('Bromsgrove District Council', 'https://www.bromsgrove.gov.uk/', 'Bromsgrove', 'Council / community'),
    CouncilEventSource('Malvern Hills District Council', 'https://www.malvernhills.gov.uk/', 'Malvern Hills', 'Council / community'),
    CouncilEventSource('Redditch Borough Council', 'https://www.redditchbc.gov.uk/', 'Redditch', 'Council / community'),
    CouncilEventSource('Wychavon District Council', 'https://www.wychavon.gov.uk/', 'Wychavon', 'Council / community'),
    CouncilEventSource('Shropshire Council', 'https://www.shropshire.gov.uk/', 'Shropshire', 'Council / community'),
    CouncilEventSource('Shrewsbury Town Council', 'https://www.shrewsburytowncouncil.gov.uk/', 'Shrewsbury', 'Town council'),
    CouncilEventSource('Telford & Wrekin Council', 'https://www.telford.gov.uk/', 'Telford', 'Council / community'),
)


def council_source_count() -> int:
    return len(COUNCIL_EVENT_SOURCES)
