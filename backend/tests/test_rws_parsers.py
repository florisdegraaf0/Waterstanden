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

