from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.api import routes
from app.api.dependencies import get_db, get_rws_client
from app.clients.rws.models import RwsLatestObservation
from app.domain.models import DailyStatistic, Measurement
from app.domain.overview import OverviewPrimarySignal, OverviewStation
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
            "water_system": "Rhine",
            "station_group": "rhine",
            "station_group_label": "Rhine",
            "significance": "Total Rhine inflow entering the Netherlands",
        }
    ]


@pytest.mark.asyncio
async def test_map_stations_endpoint_returns_group_and_anomaly_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal = OverviewPrimarySignal(
        type="seasonal_level",
        direction="high",
        value=9.37,
        unit="m NAP",
        percentile=97,
        score=94,
        message="Water level is unusually high.",
    )
    snapshot = OverviewStation(
        station_id=LOBITH_ID,
        station_name="Lobith",
        water_system="Rhine",
        latitude=51.854205,
        longitude=6.091178,
        current_value=9.37,
        unit="m NAP",
        measured_at=RECENT_MEASURED_AT,
        parameter="water_level",
        seasonal_percentile=97,
        seasonal_status="extremely_high",
        anomaly_score=94,
        anomaly_severity="high",
        anomaly_status="ok",
        anomaly_direction="high",
        confidence="high",
        data_quality_status="normal",
        freshness_status="current",
        is_rankable=True,
        delta_24h=0.63,
        primary_signal=signal,
        historical_years=10,
        historical_sample_size=150,
        recent_measurement_count=48,
    )

    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_overview_snapshots(self, parameter: str):
            assert parameter == "water_level"
            return [snapshot]

    class FakeOverviewService:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("map station loading should not refresh overview synchronously")

        async def get_overview(self, **_kwargs):  # pragma: no cover
            raise AssertionError("map station loading should not refresh overview synchronously")

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)
    monkeypatch.setattr(routes, "OverviewService", FakeOverviewService)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/map-stations")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["station_group"] == "rhine"
    assert payload[0]["significance"] == "Total Rhine inflow entering the Netherlands"
    assert payload[0]["anomaly_score"] == 94
    assert payload[0]["anomaly_severity"] == "high"
    assert payload[0]["seasonal_percentile"] == 97
    assert payload[0]["primary_signal"]["direction"] == "high"


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
    assert payload["seasonal_context"]["historical_sample_size"] == 150
    assert payload["seasonal_context"]["historical_years"] == 15
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
        "historical_sample_size": 0,
        "historical_years": 0,
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


@pytest.mark.asyncio
async def test_anomaly_endpoint_returns_explainable_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AnomalyRwsClient(FakeRwsClient):
        async def fetch_recent_measurements(
            self,
            station_code: str,
            hours: int,
        ) -> list[Measurement]:
            assert station_code == LOBITH_ID
            assert hours == 48
            variation = [-0.02, 0.0, 0.02, 0.0]
            return [
                *[
                    Measurement(
                        measured_at=RECENT_MEASURED_AT - timedelta(hours=48 - index),
                        value=8.74 + variation[index % len(variation)],
                        unit="m NAP",
                        parameter="water_level",
                        quality_code="00",
                    )
                    for index in range(24)
                ],
                *[
                    Measurement(
                        measured_at=RECENT_MEASURED_AT - timedelta(hours=23 - index),
                        value=9.37 + variation[index % len(variation)],
                        unit="m NAP",
                        parameter="water_level",
                        quality_code="00",
                    )
                    for index in range(24)
                ],
            ]

    async def anomaly_rws_client():
        yield AnomalyRwsClient()

    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_daily_statistics(self, station_external_id: str, parameter: str):
            assert station_external_id == LOBITH_ID
            assert parameter == "water_level"
            return [
                DailyStatistic(
                    date=datetime(year, RECENT_MEASURED_AT.month, RECENT_MEASURED_AT.day).date(),
                    value=5.0 + index * 0.01,
                    min_value=5.0,
                    max_value=6.0,
                    mean_value=5.5,
                    median_value=5.5,
                    observation_count=24,
                )
                for year in range(2010, 2025)
                for index in range(10)
            ]

        def list_historical_change_statistics(
            self,
            station_external_id: str,
            parameter: str,
            window_hours: int,
        ):
            from app.domain.models import HistoricalChangeStatistic

            assert station_external_id == LOBITH_ID
            assert parameter == "water_level"
            assert window_hours == 24
            return [
                HistoricalChangeStatistic(
                    date=datetime(year, RECENT_MEASURED_AT.month, RECENT_MEASURED_AT.day).date(),
                    window_hours=24,
                    delta_value=0.01,
                    observation_count=48,
                )
                for year in range(2010, 2025)
                for _index in range(4)
            ]

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)
    app.dependency_overrides[get_rws_client] = anomaly_rws_client

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/stations/{LOBITH_ID}/anomaly")

    assert response.status_code == 200
    payload = response.json()
    assert payload["anomaly"]["status"] == "ok"
    assert payload["anomaly"]["score"] >= 90
    assert {signal["type"] for signal in payload["anomaly"]["signals"]} == {
        "seasonal_level",
        "rate_of_change_24h",
    }


@pytest.mark.asyncio
async def test_anomaly_endpoint_suppresses_hydrology_for_fallback_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FallbackRwsClient(FakeRwsClient):
        async def fetch_recent_measurements(
            self,
            station_code: str,
            hours: int,
        ) -> list[Measurement]:
            return [
                Measurement(
                    measured_at=RECENT_MEASURED_AT,
                    value=9.37,
                    unit="m NAP",
                    parameter="water_level",
                    quality_code="fallback",
                )
            ]

    async def fallback_rws_client():
        yield FallbackRwsClient()

    class FakeRepository:
        def __init__(self, _db: object) -> None:
            pass

        def list_daily_statistics(self, station_external_id: str, parameter: str):
            return []

        def list_historical_change_statistics(
            self,
            station_external_id: str,
            parameter: str,
            window_hours: int,
        ):
            return []

    monkeypatch.setattr(routes, "WaterRepository", FakeRepository)
    app.dependency_overrides[get_rws_client] = fallback_rws_client

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/stations/{LOBITH_ID}/anomaly")

    assert response.status_code == 200
    payload = response.json()
    assert payload["anomaly"]["status"] == "data_quality_anomaly"
    assert payload["anomaly"]["score"] is None
    assert payload["data_quality"]["signals"][0]["type"] == "fallback_measurements"
