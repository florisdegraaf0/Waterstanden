from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.models import (
    DailyStatistic,
    PercentileReferenceValues,
    ReferencePeriod,
    SeasonalContext,
)

DEFAULT_WINDOW_DAYS = 14
DEFAULT_MIN_SAMPLE_SIZE = 150
DEFAULT_MIN_YEARS = 10


@dataclass(frozen=True)
class SeasonalConfig:
    window_days: int = DEFAULT_WINDOW_DAYS
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE
    min_years: int = DEFAULT_MIN_YEARS


def calculate_seasonal_context(
    *,
    current_value: float,
    current_date: date,
    historical_daily_values: list[DailyStatistic],
    config: SeasonalConfig | None = None,
) -> SeasonalContext:
    if config is None:
        config = SeasonalConfig()

    reference = [
        value
        for value in historical_daily_values
        if value.date.year != current_date.year
        and _is_within_seasonal_window(value.date, current_date, config.window_days)
    ]
    reference_values = [value.value for value in reference]
    years = sorted({value.date.year for value in reference})
    reference_period = ReferencePeriod(
        window_days=config.window_days,
        first_year=years[0] if years else None,
        last_year=years[-1] if years else None,
    )

    if len(reference_values) < config.min_sample_size or len(years) < config.min_years:
        return SeasonalContext(
            status="insufficient_data",
            percentile=None,
            sample_size=len(reference_values),
            years_used=len(years),
            reference_period=reference_period,
            reference_values=None,
        )

    percentile = _midrank_percentile(current_value, reference_values)
    return SeasonalContext(
        status=_status_for_percentile(percentile),
        percentile=percentile,
        sample_size=len(reference_values),
        years_used=len(years),
        reference_period=reference_period,
        reference_values=PercentileReferenceValues(
            p05=_quantile(reference_values, 0.05),
            p25=_quantile(reference_values, 0.25),
            p50=_quantile(reference_values, 0.50),
            p75=_quantile(reference_values, 0.75),
            p95=_quantile(reference_values, 0.95),
        ),
    )


def _midrank_percentile(value: float, sample: list[float]) -> float:
    less = sum(1 for item in sample if item < value)
    equal = sum(1 for item in sample if item == value)
    return 100 * (less + 0.5 * equal) / len(sample)


def _status_for_percentile(percentile: float) -> str:
    if percentile < 5:
        return "extremely_low"
    if percentile < 15:
        return "unusually_low"
    if percentile <= 85:
        return "normal"
    if percentile <= 95:
        return "unusually_high"
    return "extremely_high"


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _is_within_seasonal_window(candidate: date, target: date, window_days: int) -> bool:
    candidate_day = _seasonal_day(candidate)
    target_day = _seasonal_day(target)
    distance = abs(candidate_day - target_day)
    return min(distance, 366 - distance) <= window_days


def _seasonal_day(value: date) -> int:
    anchor = date(2000, value.month, value.day)
    return anchor.timetuple().tm_yday
