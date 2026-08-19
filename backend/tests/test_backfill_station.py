from datetime import UTC, datetime

import pytest

from app.clients.rws.models import RwsLatestObservation
from app.domain.models import Measurement
from app.jobs.backfill_station import (
    _daily_change_statistics_from_daily_statistics,
    _daily_statistics_from_measurements,
    _get_curated_station_from_latest_feed,
    _is_selected_lobith_series,
)


def test_lobith_filter_accepts_current_historical_series_metadata() -> None:
    assert _is_selected_lobith_series(
        {
            "station_code": "lobith.bovenrijn.tolkamer",
            "hoedanigheid": "NAP",
            "proces_type": "meting",
            "meetapparaat": "10042",
            "waardebepalingsmethode": None,
        }
    )


def test_lobith_filter_rejects_different_measurement_device() -> None:
    assert not _is_selected_lobith_series(
        {
            "station_code": "lobith.bovenrijn.tolkamer",
            "hoedanigheid": "NAP",
            "proces_type": "meting",
            "meetapparaat": "other",
            "waardebepalingsmethode": None,
        }
    )


@pytest.mark.asyncio
async def test_curated_backfill_metadata_accepts_stale_latest_station() -> None:
    class FakeRwsClient:
        async def fetch_latest_water_level_locations(self) -> list[RwsLatestObservation]:
            return [
                RwsLatestObservation(
                    code="pannerden.regelwerk.boven",
                    name="Pannerden, regelwerk boven",
                    latitude=51.8901,
                    longitude=6.0412,
                    value=1146,
                    unit_code="cm",
                    measured_at=datetime(2013, 11, 26, tzinfo=UTC),
                    parameter_description="Waterhoogte in Oppervlaktewater t.o.v. NAP in cm",
                    status="Ongecontroleerd",
                    quality_code="00",
                    grootheid_code="WATHTE",
                    compartiment_code="OW",
                    hoedanigheid_code="NAP",
                    raw_metadata={"source": "test"},
                )
            ]

    station = await _get_curated_station_from_latest_feed(
        FakeRwsClient(),
        "pannerden.regelwerk.boven",
    )

    assert station is not None
    assert station.id == "pannerden.regelwerk.boven"
    assert station.name == "Pannerden - regelwerk boven"
    assert station.latest_value == pytest.approx(11.46)
    assert station.metadata["source"] == "stale_latest_feed_backfill_metadata"


def test_daily_statistics_are_aggregated_from_raw_measurements() -> None:
    statistics = _daily_statistics_from_measurements(
        [
            Measurement(
                measured_at=datetime(2026, 8, 18, 1, 0, tzinfo=UTC),
                value=1.0,
                unit="m NAP",
                parameter="water_level",
            ),
            Measurement(
                measured_at=datetime(2026, 8, 18, 2, 0, tzinfo=UTC),
                value=3.0,
                unit="m NAP",
                parameter="water_level",
            ),
            Measurement(
                measured_at=datetime(2026, 8, 19, 1, 0, tzinfo=UTC),
                value=4.0,
                unit="m NAP",
                parameter="water_level",
            ),
        ]
    )

    assert len(statistics) == 2
    assert statistics[0].date.isoformat() == "2026-08-18"
    assert statistics[0].min_value == 1.0
    assert statistics[0].max_value == 3.0
    assert statistics[0].mean_value == pytest.approx(2.0)
    assert statistics[0].median_value == pytest.approx(2.0)
    assert statistics[0].observation_count == 2


def test_daily_change_statistics_use_one_daily_mean_delta_per_day() -> None:
    daily_statistics = _daily_statistics_from_measurements(
        [
            Measurement(
                measured_at=datetime(2026, 8, 18, 1, 0, tzinfo=UTC),
                value=1.0,
                unit="m NAP",
                parameter="water_level",
            ),
            Measurement(
                measured_at=datetime(2026, 8, 18, 2, 0, tzinfo=UTC),
                value=3.0,
                unit="m NAP",
                parameter="water_level",
            ),
            Measurement(
                measured_at=datetime(2026, 8, 19, 1, 0, tzinfo=UTC),
                value=5.0,
                unit="m NAP",
                parameter="water_level",
            ),
        ]
    )

    changes = _daily_change_statistics_from_daily_statistics(
        daily_statistics,
        window_hours=24,
    )

    assert len(changes) == 1
    assert changes[0].date.isoformat() == "2026-08-19"
    assert changes[0].delta_value == pytest.approx(3.0)
    assert changes[0].observation_count == 3
