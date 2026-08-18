from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest

from app.api import routes
from app.api.dependencies import get_db, get_rws_client
from app.clients.rws.models import RwsLatestObservation
from app.domain.models import DailyStatistic, Measurement
from app.main import app

RECENT_MEASURED_AT = datetime.now(UTC).replace(microsecond=0)
LOBITH_ID = "lobith.bovenrijn.tolkamer"


class FakeRwsClient:
    async def close(self) -> None:
        return None

    async def fetch_latest_water_level_locations(self) -> list[RwsLatestObservation]:
        return [
            RwsLatestObservation(
                code=LOBITH_ID,
                name="Lobith",
                latitude=51.854205,
                longitude=6.091178,
                value=937,
                unit_code="cm",
                measured_at=RECENT_MEASURED_AT,
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
        assert station_code == LOBITH_ID
        assert hours in {24, 48}
        return [
            Measurement(
                measured_at=RECENT_MEASURED_AT,
                value=9.37,
                unit="m NAP",
                parameter="water_level",
                quality_code="00",
            )
        ]


async def _fake_rws_client() -> AsyncIterator[FakeRwsClient]:
    yield FakeRwsClient()


def _fake_db():
    yield object()


@pytest.fixture(autouse=True)
def override_rws_client() -> None:
    app.dependency_overrides[get_rws_client] = _fake_rws_client
    app.dependency_overrides[get_db] = _fake_db
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
            "id": LOBITH_ID,
            "name": "Lobith",
            "latitude": 51.854205,
            "longitude": 6.091178,
            "latest_value": 9.37,
            "unit": "m NAP",
            "measured_at": RECENT_MEASURED_AT.isoformat().replace("+00:00", "Z"),
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
        response = await client.get(f"/api/stations/{LOBITH_ID}/measurements?hours=48")

    assert response.status_code == 200
    assert response.json()[0]["value"] == 9.37


@pytest.mark.asyncio
async def test_measurements_endpoint_validates_hours() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/stations/{LOBITH_ID}/measurements?hours=500")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_seasonal_context_endpoint_returns_percentile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_daily_statistics(self, station_external_id: str, parameter: str):
            assert station_external_id == LOBITH_ID
            assert parameter == "water_level"
            return [
                DailyStatistic(
                    date=datetime(year, RECENT_MEASURED_AT.month, RECENT_MEASURED_AT.day).date(),
                    value=5.0 + (year - 2010) * 0.1 + index * 0.01,
                    min_value=5.0,
                    max_value=6.0,
                    mean_value=5.5,
                    median_value=5.5,
                    observation_count=24,
                )
                for year in range(2010, 2025)
                for index in range(10)
            ]

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/stations/{LOBITH_ID}/seasonal-context",
            params={
                "current_value": 9.37,
                "current_unit": "m NAP",
                "measured_at": RECENT_MEASURED_AT.isoformat(),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["station_id"] == LOBITH_ID
    assert payload["seasonal_context"]["status"] == "extremely_high"
    assert payload["seasonal_context"]["sample_size"] == 150
    assert payload["seasonal_context"]["reference_values"]["p50"] > 0


@pytest.mark.asyncio
async def test_seasonal_context_compares_24_hour_mean_for_every_station(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DailyMeanRwsClient(FakeRwsClient):
        async def fetch_recent_measurements(
            self,
            station_code: str,
            hours: int,
        ) -> list[Measurement]:
            assert station_code == LOBITH_ID
            assert hours == 24
            return [
                Measurement(
                    measured_at=RECENT_MEASURED_AT,
                    value=value,
                    unit="m NAP",
                    parameter="water_level",
                    quality_code="00",
                )
                for value in (4.0, 5.0, 6.0)
            ]

    async def daily_mean_rws_client():
        yield DailyMeanRwsClient()

    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_daily_statistics(self, station_external_id: str, parameter: str):
            assert station_external_id == LOBITH_ID
            assert parameter == "water_level"
            return [
                DailyStatistic(
                    date=datetime(year, RECENT_MEASURED_AT.month, RECENT_MEASURED_AT.day).date(),
                    value=0.0,
                    min_value=4.0,
                    max_value=6.0,
                    mean_value=5.0,
                    median_value=0.0,
                    observation_count=24,
                )
                for year in range(2010, 2025)
                for _index in range(10)
            ]

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)
    app.dependency_overrides[get_rws_client] = daily_mean_rws_client

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/stations/{LOBITH_ID}/seasonal-context",
            params={
                "current_value": 9.37,
                "current_unit": "m NAP",
                "measured_at": RECENT_MEASURED_AT.isoformat(),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seasonal_context"]["status"] == "normal"
    assert payload["seasonal_context"]["percentile"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_seasonal_context_endpoint_handles_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_daily_statistics(self, station_external_id: str, parameter: str):
            return []

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/stations/{LOBITH_ID}/seasonal-context",
            params={
                "current_value": 9.37,
                "current_unit": "m NAP",
                "measured_at": RECENT_MEASURED_AT.isoformat(),
            },
        )

    assert response.status_code == 200
    assert response.json()["seasonal_context"] == {
        "percentile": None,
        "status": "insufficient_data",
        "sample_size": 0,
        "years_used": 0,
        "reference_period": {
            "window_days": 14,
            "first_year": None,
            "last_year": None,
        },
        "reference_values": None,
    }


@pytest.mark.asyncio
async def test_seasonal_context_endpoint_without_current_value_is_fast_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_daily_statistics(self, station_external_id: str, parameter: str):
            raise AssertionError("daily statistics should not be queried without current value")

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/stations/{LOBITH_ID}/seasonal-context")

    assert response.status_code == 200
    assert response.json()["seasonal_context"]["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_seasonal_context_endpoint_handles_missing_historical_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import ProgrammingError

    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_daily_statistics(self, station_external_id: str, parameter: str):
            raise ProgrammingError("select 1", {}, Exception("missing table"))

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/stations/{LOBITH_ID}/seasonal-context",
            params={
                "current_value": 9.37,
                "current_unit": "m NAP",
                "measured_at": RECENT_MEASURED_AT.isoformat(),
            },
        )

    assert response.status_code == 200
    assert response.json()["seasonal_context"]["status"] == "historical_data_unavailable"
