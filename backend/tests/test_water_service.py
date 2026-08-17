from datetime import UTC, datetime

import pytest

from app.clients.rws.models import RwsLatestObservation
from app.domain.models import Measurement
from app.exceptions import ExternalServiceError
from app.services.water import WaterService


class FailingRwsClient:
    async def fetch_recent_measurements(self, station_code: str, hours: int):
        raise ExternalServiceError("unavailable")


class StationRwsClient:
    async def fetch_latest_water_level_locations(self) -> list[RwsLatestObservation]:
        return [
            _observation("active", datetime(2026, 8, 17, 10, 0, tzinfo=UTC), 937),
            _observation("no-recent", datetime(2026, 8, 17, 10, 0, tzinfo=UTC), 700),
            _observation("old", datetime(2026, 8, 16, 9, 59, tzinfo=UTC), 800),
            _observation("missing", datetime(2026, 8, 17, 10, 0, tzinfo=UTC), None),
        ]

    async def fetch_recent_measurements(self, station_code: str, hours: int) -> list[Measurement]:
        if station_code != "active":
            return []
        return [
            Measurement(
                measured_at=datetime(2026, 8, 17, 9, 55, tzinfo=UTC),
                value=9.37,
                unit="m NAP",
                parameter="water_level",
                quality_code="00",
            )
        ]


@pytest.mark.asyncio
async def test_measurement_fallback_returns_marked_points_when_enabled() -> None:
    service = WaterService(FailingRwsClient(), use_fallback_measurements=True)

    measurements = await service.get_measurements("lobith", 4)

    assert measurements
    assert {measurement.quality_code for measurement in measurements} == {"fallback"}


@pytest.mark.asyncio
async def test_measurement_fallback_can_be_disabled() -> None:
    service = WaterService(FailingRwsClient(), use_fallback_measurements=False)

    with pytest.raises(ExternalServiceError):
        await service.get_measurements("lobith", 4)


@pytest.mark.asyncio
async def test_list_stations_only_includes_parsed_measurements_from_last_24_hours() -> None:
    service = WaterService(
        StationRwsClient(),
        now=datetime(2026, 8, 17, 10, 0, tzinfo=UTC),
        active_station_max_age_hours=24,
    )

    stations = await service.list_stations()

    assert [station.id for station in stations] == ["active"]
    assert stations[0].latest_value == pytest.approx(9.37)


def _observation(
    code: str,
    measured_at: datetime,
    value: float | None,
) -> RwsLatestObservation:
    return RwsLatestObservation(
        code=code,
        name=code.title(),
        latitude=51.0,
        longitude=6.0,
        value=value,
        unit_code="cm",
        measured_at=measured_at,
        parameter_description="Waterhoogte in Oppervlaktewater t.o.v. NAP in cm",
        status="Ongecontroleerd",
        quality_code="00",
        grootheid_code="WATHTE",
        compartiment_code="OW",
        hoedanigheid_code="NAP",
        raw_metadata={"source": "test"},
    )
