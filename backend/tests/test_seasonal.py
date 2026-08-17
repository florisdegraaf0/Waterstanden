from datetime import date

import pytest

from app.domain.models import DailyStatistic
from app.domain.seasonal import SeasonalConfig, calculate_seasonal_context


def daily(value_date: date, value: float) -> DailyStatistic:
    return DailyStatistic(
        date=value_date,
        value=value,
        min_value=value,
        max_value=value,
        mean_value=value,
        median_value=value,
        observation_count=1,
    )


def test_percentile_uses_midrank_for_ties() -> None:
    values = [
        daily(date(2020, 8, 17), 1.0),
        daily(date(2021, 8, 17), 2.0),
        daily(date(2022, 8, 17), 2.0),
        daily(date(2023, 8, 17), 3.0),
    ]

    result = calculate_seasonal_context(
        current_value=2.0,
        current_date=date(2026, 8, 17),
        historical_daily_values=values,
        config=SeasonalConfig(window_days=0, min_sample_size=1, min_years=1),
    )

    assert result.percentile == pytest.approx(50.0)
    assert result.status == "normal"


@pytest.mark.parametrize(
    ("current_value", "expected_status"),
    [
        (-1.0, "extremely_low"),
        (100.0, "extremely_high"),
        (18.0, "unusually_high"),
        (3.0, "unusually_low"),
    ],
)
def test_status_thresholds(current_value: float, expected_status: str) -> None:
    values = [daily(date(2000 + index, 8, 17), float(index)) for index in range(1, 21)]

    result = calculate_seasonal_context(
        current_value=current_value,
        current_date=date(2026, 8, 17),
        historical_daily_values=values,
        config=SeasonalConfig(window_days=0, min_sample_size=1, min_years=1),
    )

    assert result.status == expected_status


def test_insufficient_sample_size_returns_metadata_without_percentile() -> None:
    values = [daily(date(2020, 8, 17), 1.0)]

    result = calculate_seasonal_context(
        current_value=2.0,
        current_date=date(2026, 8, 17),
        historical_daily_values=values,
        config=SeasonalConfig(window_days=14, min_sample_size=2, min_years=2),
    )

    assert result.status == "insufficient_data"
    assert result.percentile is None
    assert result.sample_size == 1
    assert result.years_used == 1


def test_excludes_current_year() -> None:
    values = [
        daily(date(2025, 8, 17), 1.0),
        daily(date(2026, 8, 17), 100.0),
    ]

    result = calculate_seasonal_context(
        current_value=2.0,
        current_date=date(2026, 8, 17),
        historical_daily_values=values,
        config=SeasonalConfig(window_days=0, min_sample_size=1, min_years=1),
    )

    assert result.sample_size == 1
    assert result.percentile == pytest.approx(100.0)


def test_seasonal_window_wraps_across_year_boundary() -> None:
    values = [
        daily(date(2020, 12, 31), 1.0),
        daily(date(2021, 1, 1), 2.0),
        daily(date(2022, 1, 3), 3.0),
    ]

    result = calculate_seasonal_context(
        current_value=2.5,
        current_date=date(2026, 1, 1),
        historical_daily_values=values,
        config=SeasonalConfig(window_days=1, min_sample_size=1, min_years=1),
    )

    assert result.sample_size == 2


def test_leap_day_window_matches_nearby_dates() -> None:
    values = [
        daily(date(2020, 2, 29), 1.0),
        daily(date(2021, 3, 1), 2.0),
        daily(date(2022, 3, 3), 3.0),
    ]

    result = calculate_seasonal_context(
        current_value=2.5,
        current_date=date(2024, 2, 29),
        historical_daily_values=values,
        config=SeasonalConfig(window_days=1, min_sample_size=1, min_years=1),
    )

    assert result.sample_size == 2


def test_uses_only_values_inside_configured_window() -> None:
    current = date(2026, 8, 17)
    values = [
        daily(date(2020, 8, 10), 1.0),
        daily(date(2021, 8, 24), 2.0),
        daily(date(2022, 9, 20), 100.0),
    ]

    result = calculate_seasonal_context(
        current_value=1.5,
        current_date=current,
        historical_daily_values=values,
        config=SeasonalConfig(window_days=7, min_sample_size=1, min_years=1),
    )

    assert result.sample_size == 2
    assert result.percentile == pytest.approx(50.0)


def test_reference_values_are_quantiles() -> None:
    values = [daily(date(2000 + index, 8, 17), float(index)) for index in range(1, 21)]

    result = calculate_seasonal_context(
        current_value=10.0,
        current_date=date(2026, 8, 17),
        historical_daily_values=values,
        config=SeasonalConfig(window_days=0, min_sample_size=1, min_years=1),
    )

    assert result.reference_values is not None
    assert result.reference_values.p50 == pytest.approx(10.5)
