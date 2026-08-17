from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest

from app.api.dependencies import get_rws_client
from app.clients.rws.models import RwsLatestObservation
from app.domain.models import Measurement
from app.main import app


class FakeRwsClient:
    async def close(self) -> None:
        return None

    async def fetch_latest_water_level_locations(self) -> list[RwsLatestObservation]:
        return [
            RwsLatestObservation(
                code="lobith",
                name="Lobith",
                latitude=51.854205,
                longitude=6.091178,
                value=937,
                unit_code="cm",
                measured_at=datetime(2026, 8, 17, 10, 0, tzinfo=UTC),
                parameter_description="Waterhoogte in Oppervlaktewater t.o.v. NAP in cm",
                status="Ongecontroleerd",
                quality_code="00",
                grootheid_code="WATHTE",
                compartiment_code="OW",
                hoedanigheid_code="NAP",
                raw_metadata={"source": "test"},
            )
        ]

    async def fetch_recent_measurements(self, station_code: str, hours: int) -> list[Measurement]:
        assert station_code == "lobith"
        assert hours == 48
        return [
            Measurement(
                measured_at=datetime(2026, 8, 17, 10, 0, tzinfo=UTC),
                value=9.37,
                unit="m NAP",
                parameter="water_level",
                quality_code="00",
            )
        ]


async def _fake_rws_client() -> AsyncIterator[FakeRwsClient]:
    yield FakeRwsClient()


@pytest.fixture(autouse=True)
def override_rws_client() -> None:
    app.dependency_overrides[get_rws_client] = _fake_rws_client
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_stations_endpoint_returns_normalized_stations() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/stations")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "lobith",
            "name": "Lobith",
            "latitude": 51.854205,
            "longitude": 6.091178,
            "latest_value": 9.37,
            "unit": "m NAP",
            "measured_at": "2026-08-17T10:00:00Z",
            "parameter": "water_level",
            "status": "Ongecontroleerd",
            "quality_code": "00",
        }
    ]


@pytest.mark.asyncio
async def test_measurements_endpoint_returns_recent_points() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/stations/lobith/measurements?hours=48")

    assert response.status_code == 200
    assert response.json()[0]["value"] == 9.37


@pytest.mark.asyncio
async def test_measurements_endpoint_validates_hours() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/stations/lobith/measurements?hours=500")

    assert response.status_code == 422

