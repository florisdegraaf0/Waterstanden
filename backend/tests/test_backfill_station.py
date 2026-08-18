from datetime import UTC, datetime

import pytest

from app.domain.models import Measurement
from app.jobs.backfill_station import (
    _daily_statistics_from_measurements,
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
