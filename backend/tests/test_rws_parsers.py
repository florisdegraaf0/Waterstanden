import json
from pathlib import Path

import pytest

from app.clients.rws.parsers import (
    normalize_latest_water_level,
    parse_latest_observations_csv,
    parse_observations_response,
)
from app.exceptions import ExternalDataError

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_latest_observations_filters_and_normalizes_water_levels() -> None:
    rows = parse_latest_observations_csv((FIXTURES / "latest_observations.csv").read_text())

    assert len(rows) == 1
    assert rows[0].code == "grijpskerk.gaarkeuken.oost"
    assert rows[0].latitude == 53.24909
    assert rows[0].longitude == 6.317575

    measurement = normalize_latest_water_level(rows[0])
    assert measurement is not None
    assert measurement.value == pytest.approx(-0.79)
    assert measurement.unit == "m NAP"


def test_parse_latest_observations_rejects_missing_required_fields() -> None:
    csv_text = (
        "CODE;NAAM;GROOTHEIDCODE;COMPARTIMENTCODE;KWALITEITSWAARDE_CODE;GEOMETRY;"
        "PARAMETER_WAT_OMSCHRIJVING\n"
        "station;;WATHTE;OW;00;POINT (52.0 5.0);Waterhoogte\n"
    )

    with pytest.raises(ExternalDataError):
        parse_latest_observations_csv(csv_text)


def test_parse_recent_observations_response() -> None:
    payload = json.loads((FIXTURES / "recent_observations.json").read_text())

    measurements = parse_observations_response(payload)

    assert [measurement.value for measurement in measurements] == [1.2, 1.23]
    assert all(measurement.unit == "m NAP" for measurement in measurements)
    assert measurements[0].quality_code == "00"


def test_parse_discharge_observations_response() -> None:
    payload = {
        "WaarnemingenLijst": [
            {
                "Locatie": {
                    "Naam": "Lobith, Bovenrijn, Tolkamer",
                    "Code": "lobith.bovenrijn.tolkamer",
                },
                "AquoMetadata": {
                    "Compartiment": {"Code": "OW"},
                    "Eenheid": {"Code": "m3/s"},
                    "Grootheid": {"Code": "Q"},
                    "Hoedanigheid": {"Code": "NVT"},
                    "MeetApparaat": {"Code": "8000"},
                    "ProcesType": "meting",
                    "WaardeBepalingsmethode": {"Code": "other:F230"},
                    "WaardeBewerkingsmethode": {"Code": "NVT"},
                },
                "MetingenLijst": [
                    {
                        "Tijdstip": "2026-08-20T15:00:00.000Z",
                        "Meetwaarde": {"Waarde_Numeriek": 612.17},
                        "WaarnemingMetadata": {
                            "Kwaliteitswaardecode": {"Code": "00"},
                        },
                    }
                ],
            }
        ]
    }

    measurements = parse_observations_response(payload)

    assert len(measurements) == 1
    assert measurements[0].parameter == "discharge"
    assert measurements[0].value == pytest.approx(612.17)
    assert measurements[0].unit == "m3/s"
    assert measurements[0].source_metadata["grootheid"] == "Q"


def test_unknown_rws_parameter_is_rejected() -> None:
    payload = {
        "WaarnemingenLijst": [
            {
                "AquoMetadata": {
                    "Compartiment": {"Code": "OW"},
                    "Eenheid": {"Code": "m3/s"},
                    "Grootheid": {"Code": "NOT_Q"},
                },
                "MetingenLijst": [],
            }
        ]
    }

    with pytest.raises(ExternalDataError):
        parse_observations_response(payload)


def test_parse_historical_observations_preserves_source_metadata() -> None:
    payload = {
        "WaarnemingenLijst": [
            {
                "Locatie": {
                    "Naam": "Lobith, Bovenrijn, Tolkamer",
                    "Code": "lobith.bovenrijn.tolkamer",
                },
                "AquoMetadata": {
                    "Compartiment": {"Code": "OW"},
                    "Eenheid": {"Code": "cm"},
                    "Grootheid": {"Code": "WATHTE"},
                    "Hoedanigheid": {"Code": "NAP"},
                    "MeetApparaat": {"Code": "10042"},
                    "ProcesType": "meting",
                    "WaardeBepalingsmethode": {"Code": "other:F007"},
                    "WaardeBewerkingsmethode": {"Code": "NVT"},
                },
                "WaarnemingMetadata": {
                    "OpdrachtgevendeInstantieLijst": [{"Code": "RIKZMON_WAT"}],
                    "BemonsteringshoogteLijst": ["0"],
                },
                "MetingenLijst": [
                    {
                        "Tijdstip": "2025-08-17T01:00:00.000Z",
                        "Meetwaarde": {"Waarde_Numeriek": 781},
                        "WaarnemingMetadata": {
                            "Kwaliteitswaardecode": {"Code": "00"},
                        },
                    },
                    {
                        "Tijdstip": "2025-08-17T01:10:00.000Z",
                        "Meetwaarde": {"Waarde_Numeriek": ""},
                    },
                ],
            }
        ]
    }

    measurements = parse_observations_response(payload)

    assert len(measurements) == 1
    assert measurements[0].value == pytest.approx(7.81)
    assert measurements[0].source_station_code == "lobith.bovenrijn.tolkamer"
    assert measurements[0].source_unit == "cm"
    assert measurements[0].source_metadata == {
        "source": "rws_ddapi20_waterwebservices_observations",
        "station_code": "lobith.bovenrijn.tolkamer",
        "station_name": "Lobith, Bovenrijn, Tolkamer",
        "unit": "cm",
        "grootheid": "WATHTE",
        "compartiment": "OW",
        "hoedanigheid": "NAP",
        "proces_type": "meting",
        "meetapparaat": "10042",
        "waardebepalingsmethode": "other:F007",
        "waardebewerkingsmethode": "NVT",
        "opdrachtgevende_instantie": "RIKZMON_WAT",
        "bemonsteringshoogte": "0",
    }
