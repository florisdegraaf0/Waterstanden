from datetime import UTC, datetime

import httpx
import pytest

from app.api import routes
from app.api.dependencies import get_db, get_rws_client
from app.domain.overview import (
    OverviewCoverage,
    OverviewPrimarySignal,
    OverviewResult,
    OverviewStation,
    OverviewSummary,
)
from app.main import app
from app.services.overview import _build_overview_result

GENERATED_AT = datetime(2026, 8, 19, 13, 30, tzinfo=UTC)


def overview_station(
    station_id: str,
    *,
    score: int | None,
    seasonal_percentile: float | None,
    severity: str = "normal",
    status: str = "ok",
    seasonal_status: str = "normal",
    signal: OverviewPrimarySignal | None = None,
    stale: bool = False,
) -> OverviewStation:
    return OverviewStation(
        station_id=station_id,
        station_name=station_id,
        water_system="Rhine",
        latitude=51.0,
        longitude=5.0,
        current_value=1.23,
        unit="m NAP",
        measured_at=GENERATED_AT,
        parameter="water_level",
        seasonal_percentile=seasonal_percentile,
        seasonal_status=seasonal_status,
        anomaly_score=score,
        anomaly_severity=severity,
        anomaly_status=status,
        anomaly_direction=signal.direction if signal else None,
        confidence="high",
        data_quality_status="data_quality_anomaly" if stale else "normal",
        freshness_status="stale" if stale else "current",
        is_rankable=score is not None and not stale and status == "ok",
        delta_24h=signal.value if signal and signal.type == "rate_of_change_24h" else None,
        primary_signal=signal,
        historical_years=10 if score is not None else 0,
        historical_sample_size=150 if score is not None else 0,
        recent_measurement_count=48,
    )


def change_signal(direction: str, value: float, score: int = 90) -> OverviewPrimarySignal:
    return OverviewPrimarySignal(
        type="rate_of_change_24h",
        direction=direction,
        value=value,
        unit="m",
        percentile=95,
        score=score,
        message="Rapid movement",
    )


def test_overview_ranks_by_anomaly_score_and_excludes_stale_or_insufficient_rows() -> None:
    result = _build_overview_result(
        generated_at=GENERATED_AT,
        stations=[
            overview_station(
                "lobith.bovenrijn.tolkamer",
                score=80,
                seasonal_percentile=90,
                severity="high",
            ),
            overview_station(
                "maastricht.borgharen.maas.beneden",
                score=96,
                seasonal_percentile=99,
                severity="extreme",
                stale=True,
            ),
            overview_station(
                "hoekvanholland",
                score=None,
                seasonal_percentile=None,
                status="insufficient_data",
            ),
            overview_station(
                "vlissingen",
                score=90,
                seasonal_percentile=5,
                severity="high",
            ),
        ],
        overview_filter="all",
        sort="anomaly_score",
        limit=10,
    )

    assert [station.station_id for station in result.stations] == [
        "vlissingen",
        "lobith.bovenrijn.tolkamer",
    ]
    assert result.summary.stations_monitored == 4
    assert result.summary.high_or_extreme_anomalies == 2
    assert result.summary.data_limited_or_stale == 2
    assert result.coverage.stale_stations == 1
    assert result.coverage.insufficient_data_stations == 1


def test_overview_treats_low_and_high_percentiles_symmetrically_for_seasonal_sort() -> None:
    result = _build_overview_result(
        generated_at=GENERATED_AT,
        stations=[
            overview_station("lobith.bovenrijn.tolkamer", score=80, seasonal_percentile=90),
            overview_station("maastricht.borgharen.maas.beneden", score=80, seasonal_percentile=10),
            overview_station("hoekvanholland", score=20, seasonal_percentile=60),
        ],
        overview_filter="all",
        sort="seasonal_unusualness",
        limit=10,
    )

    assert [station.station_id for station in result.stations[:2]] == [
        "lobith.bovenrijn.tolkamer",
        "maastricht.borgharen.maas.beneden",
    ]


def test_overview_filters_rapid_movement() -> None:
    result = _build_overview_result(
        generated_at=GENERATED_AT,
        stations=[
            overview_station(
                "lobith.bovenrijn.tolkamer",
                score=91,
                seasonal_percentile=80,
                signal=change_signal("rising", 0.63),
            ),
            overview_station(
                "maastricht.borgharen.maas.beneden",
                score=89,
                seasonal_percentile=20,
                signal=change_signal("falling", -0.21),
            ),
        ],
        overview_filter="rapidly_falling",
        sort="largest_24h_fall",
        limit=10,
    )

    assert [station.station_id for station in result.stations] == [
        "maastricht.borgharen.maas.beneden"
    ]
    assert result.summary.rapidly_rising == 1
    assert result.summary.rapidly_falling == 1


class FakeRwsClient:
    async def close(self) -> None:
        return None


async def _fake_rws_client():
    yield FakeRwsClient()


def _fake_db():
    yield object()


@pytest.fixture(autouse=True)
def override_dependencies():
    app.dependency_overrides[get_rws_client] = _fake_rws_client
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_overview_endpoint_returns_summary_and_station_rows(monkeypatch: pytest.MonkeyPatch):
    class FakeOverviewService:
        def __init__(self, **_kwargs) -> None:
            pass

        async def get_overview(self, **_kwargs) -> OverviewResult:
            station = overview_station(
                "lobith.bovenrijn.tolkamer",
                score=94,
                seasonal_percentile=97,
                severity="high",
                seasonal_status="extremely_high",
                signal=change_signal("rising", 0.63),
            )
            return OverviewResult(
                generated_at=GENERATED_AT,
                summary=OverviewSummary(
                    stations_monitored=1,
                    high_or_extreme_anomalies=1,
                    extreme_anomalies=0,
                    rapidly_rising=1,
                    rapidly_falling=0,
                    data_limited_or_stale=0,
                ),
                coverage=OverviewCoverage(
                    historical_context_stations=1,
                    insufficient_data_stations=0,
                    stale_stations=0,
                    rankable_stations=1,
                ),
                stations=[station],
            )

    monkeypatch.setattr(routes, "OverviewService", FakeOverviewService)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["stations_monitored"] == 1
    assert payload["coverage"]["rankable_stations"] == 1
    assert payload["stations"][0]["station_name"] == "lobith.bovenrijn.tolkamer"
    assert payload["stations"][0]["primary_signal"]["direction"] == "rising"
