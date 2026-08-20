from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.anomaly import (
    AnomalyConfig,
    ChangeReference,
    build_anomaly_result,
    calculate_change_reference,
    calculate_recent_features,
    detect_data_quality,
    percentile_to_anomaly_score,
    severity_for_score,
)
from app.domain.models import HistoricalChangeStatistic, Measurement, ReferencePeriod


def measurement(at: datetime, value: float, quality_code: str | None = "00") -> Measurement:
    return Measurement(
        measured_at=at,
        value=value,
        unit="m NAP",
        parameter="water_level",
        quality_code=quality_code,
    )


@pytest.mark.parametrize(
    ("percentile", "score"),
    [
        (50.0, 0),
        (75.0, 50),
        (90.0, 80),
        (97.0, 94),
        (99.0, 98),
        (1.0, 98),
    ],
)
def test_percentile_maps_to_symmetric_anomaly_score(percentile: float, score: int) -> None:
    assert percentile_to_anomaly_score(percentile) == score


@pytest.mark.parametrize(
    ("score", "severity"),
    [(0, "normal"), (30, "low"), (60, "moderate"), (80, "high"), (95, "extreme")],
)
def test_severity_thresholds(score: int, severity: str) -> None:
    assert severity_for_score(score) == severity


def test_24h_delta_uses_window_means_to_avoid_tidal_point_mismatch() -> None:
    current_at = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    cycle = [0.0, 1.0, 0.0, -1.0] * 3
    features = calculate_recent_features(
        current=measurement(current_at, cycle[-1]),
        recent_measurements=[
            *[
                measurement(current_at - timedelta(hours=48 - index * 2), value)
                for index, value in enumerate(cycle)
            ],
            *[
                measurement(current_at - timedelta(hours=22 - index * 2), value)
                for index, value in enumerate(cycle)
            ],
        ],
        evaluated_at=current_at,
        config=AnomalyConfig(),
    )

    assert features.delta_24h == pytest.approx(0.0)


def test_24h_delta_is_missing_without_enough_window_coverage() -> None:
    current_at = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    features = calculate_recent_features(
        current=measurement(current_at, 9.37),
        recent_measurements=[
            measurement(current_at - timedelta(hours=30), 8.80),
            measurement(current_at - timedelta(hours=28), 8.90),
            measurement(current_at - timedelta(hours=2), 9.30),
            measurement(current_at, 9.37),
        ],
        evaluated_at=current_at,
        config=AnomalyConfig(),
    )

    assert features.delta_24h is None


def test_historical_change_reference_filters_by_station_season_and_previous_years() -> None:
    current_date = date(2026, 8, 18)
    changes = [
        HistoricalChangeStatistic(
            date=date(year, 8, 18),
            window_hours=24,
            delta_value=0.01,
            observation_count=2,
        )
        for year in range(2010, 2025)
        for _ in range(4)
    ]
    changes.append(
        HistoricalChangeStatistic(
            date=date(2026, 8, 18),
            window_hours=24,
            delta_value=100,
            observation_count=2,
        )
    )

    reference = calculate_change_reference(
        current_delta=0.50,
        current_date=current_date,
        historical_changes=changes,
        config=AnomalyConfig(seasonal_window_days=0),
    )

    assert reference.status == "ok"
    assert reference.sample_size == 60
    assert reference.years_used == 15
    assert reference.percentile == pytest.approx(100.0)


def test_historical_change_reference_requires_minimum_history() -> None:
    reference = calculate_change_reference(
        current_delta=0.50,
        current_date=date(2026, 8, 18),
        historical_changes=[
            HistoricalChangeStatistic(
                date=date(2020, 8, 18),
                window_hours=24,
                delta_value=0.01,
                observation_count=2,
            )
        ],
        config=AnomalyConfig(seasonal_window_days=0),
    )

    assert reference.status == "insufficient_data"
    assert reference.percentile is None


def test_combined_score_uses_level_and_change_weights() -> None:
    features = calculate_recent_features(
        current=measurement(datetime(2026, 8, 18, 10, 0, tzinfo=UTC), 9.37),
        recent_measurements=[],
        evaluated_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
        config=AnomalyConfig(),
    )

    result, _quality = build_anomaly_result(
        level_percentile=97,
        level_status="extremely_high",
        level_sample_size=150,
        level_years_used=10,
        level_value=9.37,
        level_unit="m NAP",
        change_reference=ChangeReference(
            status="ok",
            percentile=99,
            sample_size=100,
            years_used=10,
            reference_period=ReferencePeriod(14, 2010, 2025),
        ),
        delta_24h=0.63,
        features=features,
        data_quality_status="normal",
        data_quality_signals=[],
    )

    assert result.score == 96
    assert result.severity == "extreme"
    assert result.confidence == "high"


def test_severe_data_quality_suppresses_hydrological_score() -> None:
    now = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    current = measurement(now - timedelta(hours=4), 9.37)
    features = calculate_recent_features(
        current=current,
        recent_measurements=[current],
        evaluated_at=now,
        config=AnomalyConfig(stale_after_minutes=180),
    )
    status, signals = detect_data_quality(
        current=current,
        recent_measurements=[current],
        features=features,
        config=AnomalyConfig(stale_after_minutes=180),
    )

    result, _quality = build_anomaly_result(
        level_percentile=99,
        level_status="extremely_high",
        level_sample_size=150,
        level_years_used=10,
        level_value=9.37,
        level_unit="m NAP",
        change_reference=ChangeReference(
            status="ok",
            percentile=99,
            sample_size=100,
            years_used=10,
            reference_period=ReferencePeriod(14, 2010, 2025),
        ),
        delta_24h=0.63,
        features=features,
        data_quality_status=status,
        data_quality_signals=signals,
    )

    assert status == "data_quality_anomaly"
    assert result.score is None
    assert result.status == "data_quality_anomaly"
