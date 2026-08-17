import pytest

from app.exceptions import ExternalServiceError
from app.services.water import WaterService


class FailingRwsClient:
    async def fetch_recent_measurements(self, station_code: str, hours: int):
        raise ExternalServiceError("unavailable")


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

