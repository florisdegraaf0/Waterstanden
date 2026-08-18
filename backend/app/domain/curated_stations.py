from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedStation:
    id: str
    display_name: str
    water_system: str
    significance: str
    sort_order: int


CURATED_STATIONS: tuple[CuratedStation, ...] = (
    CuratedStation(
        "lobith.bovenrijn.tolkamer",
        "Lobith",
        "Rhine",
        "Total Rhine inflow entering the Netherlands",
        1,
    ),
    CuratedStation(
        "maastricht.borgharen.maas.beneden",
        "Borgharen-Dorp",
        "Maas",
        "Maas water level immediately downstream of Belgium",
        2,
    ),
    CuratedStation(
        "hoekvanholland",
        "Hoek van Holland",
        "North Sea/Rijnmond",
        "Storm surge, tide and Rhine-Meuse delta boundary",
        3,
    ),
    CuratedStation(
        "vlissingen",
        "Vlissingen",
        "Western Scheldt",
        "Scheldt estuary tides and coastal storm surge",
        4,
    ),
    CuratedStation(
        "ijmuiden.buitenhaven",
        "IJmuiden",
        "North Sea/Noordzeekanaal",
        "Central coast and Noordzeekanaal entrance",
        5,
    ),
    CuratedStation(
        "delfzijl",
        "Delfzijl",
        "Ems estuary",
        "Northeastern coastal flood risk",
        6,
    ),
    CuratedStation(
        "denhelder.marsdiep",
        "Den Helder",
        "North Sea/Wadden Sea",
        "North Sea-Wadden Sea exchange",
        7,
    ),
    CuratedStation(
        "harlingen.waddenzee",
        "Harlingen",
        "Wadden Sea",
        "Central Wadden Sea and Frisian coast",
        8,
    ),
    CuratedStation(
        "pannerden.regelwerk.boven",
        "Pannerden - regelwerk boven",
        "Rhine distributaries",
        "Rhine-water distribution toward Waal and Pannerdensch Kanaal",
        9,
    ),
    CuratedStation(
        "westervoort.ijsselkop",
        "IJsselkop",
        "IJssel/Nederrijn",
        "Distribution between IJssel and Nederrijn",
        10,
    ),
    CuratedStation(
        "nijmegen.waal",
        "Nijmegen-Haven",
        "Waal",
        "Upper Waal level and navigation conditions",
        11,
    ),
    CuratedStation(
        "tiel.waal",
        "Tiel-Waal",
        "Waal",
        "Middle Waal; useful propagation point downstream of Nijmegen",
        12,
    ),
    CuratedStation(
        "dordrecht.oudemaas.benedenmerwede",
        "Dordrecht",
        "Beneden-Merwede/Oude Maas",
        "River discharge combined with tidal influence",
        13,
    ),
    CuratedStation(
        "westervoort.hondsbroekschepleij.ijssel",
        "Hondsbroeksche Pleij-IJssel",
        "IJssel",
        "Upper IJssel after the main Rhine bifurcation",
        14,
    ),
    CuratedStation(
        "zwolle.ijssel",
        "Katerveer",
        "IJssel",
        "Lower IJssel before it reaches the IJsselmeer",
        15,
    ),
    CuratedStation(
        "roermond.boven",
        "Roermond-boven",
        "Maas",
        "Central Limburg and Roer-Maas system",
        16,
    ),
    CuratedStation(
        "venlo",
        "Venlo",
        "Maas",
        "Northern Limburg; important high-water reference",
        17,
    ),
    CuratedStation(
        "grave.beneden",
        "Grave-beneden",
        "Maas",
        "Lower, heavily regulated Maas",
        18,
    ),
    CuratedStation(
        "lith.beneden",
        "Lith-Dorp",
        "Maas",
        "Final regulated reach before the lower-river area",
        19,
    ),
    CuratedStation(
        "rotterdam.nieuwemaas.boerengat",
        "Rotterdam - Nieuwe Maas/Boerengat",
        "Rijnmond",
        "Urban Rotterdam and tidal penetration inland",
        20,
    ),
    CuratedStation(
        "moerdijk",
        "Moerdijk",
        "Hollandsch Diep",
        "Connection between river discharge and southwest delta",
        21,
    ),
    CuratedStation(
        "hellevoetsluis",
        "Hellevoetsluis",
        "Haringvliet",
        "Haringvliet control, tides and delta water management",
        22,
    ),
    CuratedStation(
        "denoever.ijsselmeer.binnenhaven",
        "Den Oever-binnen",
        "IJsselmeer",
        "IJsselmeer level at the Afsluitdijk",
        23,
    ),
    CuratedStation(
        "lemmer.ijsselmeer",
        "Lemmer",
        "IJsselmeer",
        "Eastern IJsselmeer and freshwater management",
        24,
    ),
    CuratedStation(
        "lelystad.houtribsluis.noord",
        "Lelystad-Haven",
        "Markermeer",
        "Markermeer level and wind-induced setup",
        25,
    ),
)

CURATED_STATION_BY_ID = {station.id: station for station in CURATED_STATIONS}
CURATED_STATION_IDS = frozenset(CURATED_STATION_BY_ID)
