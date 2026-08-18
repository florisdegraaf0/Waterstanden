from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median

from app.domain.models import (
    AnomalyDataQuality,
    AnomalyResult,
    AnomalySignal,
    HistoricalChangeStatistic,
    Measurement,
    ReferencePeriod,
)
from app.domain.seasonal import is_within_seasonal_window, midrank_percentile

LEVEL_WEIGHT = 0.55
CHANGE_WEIGHT = 0.45
DELTA_WINDOW_HOURS = 24
DELTA_MIN_SAMPLE_SIZE = 50
DELTA_MIN_YEARS = 5
DELTA_HIGH_CONFIDENCE_SAMPLE_SIZE = 100
DELTA_HIGH_CONFIDENCE_YEARS = 10


@dataclass(frozen=True)
class AnomalyConfig:
    seasonal_window_days: int = 14
    delta_tolerance_minutes: int = 45
    recent_window_hours: int = 48
    stale_after_minutes: int = 180


@dataclass(frozen=True)
class RecentFeatures:
    current_level: float | None
    delta_24h: float | None
    latest_measurement_age_minutes: float | None
    recent_observation_count: int
    largest_recent_gap_minutes: float | None


@dataclass(frozen=True)
class ChangeReference:
    status: str
    percentile: float | None
    sample_size: int
    years_used: int
    reference_period: ReferencePeriod


def calculate_recent_features(
    *,
    current: Measurement,
    recent_measurements: list[Measurement],
    evaluated_at: datetime,
    config: AnomalyConfig,
    parameter: str = "water_level",
) -> RecentFeatures:
    measurements = sorted(
        (measurement for measurement in recent_measurements if measurement.parameter == parameter),
        key=lambda measurement: measurement.measured_at,
    )
    target = current.measured_at - timedelta(hours=DELTA_WINDOW_HOURS)
    comparison = _nearest_measurement(
        measurements,
        target=target,
        tolerance=timedelta(minutes=config.delta_tolerance_minutes),
    )
    return RecentFeatures(
        current_level=current.value,
        delta_24h=current.value - comparison.value if comparison is not None else None,
        latest_measurement_age_minutes=max(
            (evaluated_at - current.measured_at).total_seconds() / 60,
            0,
        ),
        recent_observation_count=len(measurements),
        largest_recent_gap_minutes=_largest_gap_minutes(measurements),
    )


def calculate_change_reference(
    *,
    current_delta: float | None,
    current_date: date,
    historical_changes: list[HistoricalChangeStatistic],
    config: AnomalyConfig,
) -> ChangeReference:
    reference = [
        change
        for change in historical_changes
        if change.window_hours == DELTA_WINDOW_HOURS
        and change.date.year != current_date.year
        and is_within_seasonal_window(change.date, current_date, config.seasonal_window_days)
    ]
    years = sorted({change.date.year for change in reference})
    reference_period = ReferencePeriod(
        window_days=config.seasonal_window_days,
        first_year=years[0] if years else None,
        last_year=years[-1] if years else None,
    )
    if (
        current_delta is None
        or len(reference) < DELTA_MIN_SAMPLE_SIZE
        or len(years) < DELTA_MIN_YEARS
    ):
        return ChangeReference(
            status="insufficient_data",
            percentile=None,
            sample_size=len(reference),
            years_used=len(years),
            reference_period=reference_period,
        )
    return ChangeReference(
        status="ok",
        percentile=midrank_percentile(current_delta, [change.delta_value for change in reference]),
        sample_size=len(reference),
        years_used=len(years),
        reference_period=reference_period,
    )


def detect_data_quality(
    *,
    current: Measurement,
    recent_measurements: list[Measurement],
    features: RecentFeatures,
    config: AnomalyConfig,
) -> tuple[str, list[AnomalySignal]]:
    signals: list[AnomalySignal] = []
    severe = False
    measurements = sorted(recent_measurements, key=lambda measurement: measurement.measured_at)

    if (
        features.latest_measurement_age_minutes is not None
        and features.latest_measurement_age_minutes > config.stale_after_minutes
    ):
        severe = True
        signals.append(
            _quality_signal(
                "stale_latest_measurement",
                "Latest measurement is stale, so hydrological anomaly scoring is suppressed.",
                value=features.latest_measurement_age_minutes,
                unit="minutes",
            )
        )

    if current.quality_code == "fallback" or any(
        measurement.quality_code == "fallback" for measurement in measurements
    ):
        severe = True
        signals.append(
            _quality_signal(
                "fallback_measurements",
                "Recent measurements are fallback values, not observed sensor data.",
            )
        )

    if len({measurement.measured_at for measurement in measurements}) < len(measurements):
        severe = True
        signals.append(
            _quality_signal(
                "duplicate_timestamps",
                "Recent measurements contain duplicate timestamps.",
            )
        )

    if _is_flatline(measurements):
        severe = True
        signals.append(
            _quality_signal(
                "flatline",
                "Recent measurements are nearly unchanged for an extended period.",
            )
        )

    if _has_isolated_latest_spike(measurements):
        severe = True
        signals.append(
            _quality_signal(
                "isolated_spike",
                "The latest measurement is an isolated spike compared with adjacent values.",
            )
        )

    if _has_large_gap(measurements):
        signals.append(
            _quality_signal(
                "large_recent_gap",
                "Recent measurements contain a larger-than-normal time gap.",
                value=features.largest_recent_gap_minutes,
                unit="minutes",
            )
        )

    return ("data_quality_anomaly" if severe else "degraded" if signals else "normal"), signals


def build_anomaly_result(
    *,
    level_percentile: float | None,
    level_status: str,
    level_sample_size: int,
    level_years_used: int,
    level_value: float,
    level_unit: str,
    change_reference: ChangeReference,
    delta_24h: float | None,
    features: RecentFeatures,
    data_quality_status: str,
    data_quality_signals: list[AnomalySignal],
) -> tuple[AnomalyResult, AnomalyDataQuality]:
    data_quality = AnomalyDataQuality(
        status=data_quality_status,
        signals=data_quality_signals,
        historical_years=max(level_years_used, change_reference.years_used),
        historical_sample_size=max(level_sample_size, change_reference.sample_size),
        recent_measurement_count=features.recent_observation_count,
        largest_recent_gap_minutes=features.largest_recent_gap_minutes,
    )

    if data_quality_status == "data_quality_anomaly":
        return (
            AnomalyResult(
                status="data_quality_anomaly",
                score=None,
                severity="normal",
                is_anomalous=False,
                confidence="low",
                signals=data_quality_signals,
            ),
            data_quality,
        )

    signals: list[AnomalySignal] = []
    component_scores: list[tuple[float, int]] = []
    if level_percentile is not None and level_status not in {
        "insufficient_data",
        "historical_data_unavailable",
    }:
        level_score = percentile_to_anomaly_score(level_percentile)
        component_scores.append((LEVEL_WEIGHT, level_score))
        signals.append(
            AnomalySignal(
                type="seasonal_level",
                category="hydrological",
                score=level_score,
                direction="high" if level_percentile > 50 else "low",
                value=level_value,
                unit=level_unit,
                percentile=level_percentile,
                message=_level_message(level_percentile),
            )
        )

    if change_reference.percentile is not None and delta_24h is not None:
        change_score = percentile_to_anomaly_score(change_reference.percentile)
        component_scores.append((CHANGE_WEIGHT, change_score))
        signals.append(
            AnomalySignal(
                type="rate_of_change_24h",
                category="hydrological",
                score=change_score,
                direction="rising" if delta_24h >= 0 else "falling",
                value=delta_24h,
                unit="m",
                percentile=change_reference.percentile,
                message=_change_message(delta_24h, change_reference.percentile),
            )
        )

    if not component_scores:
        status = (
            "historical_data_unavailable"
            if level_status == "historical_data_unavailable"
            else "insufficient_data"
        )
        return (
            AnomalyResult(
                status=status,
                score=None,
                severity="normal",
                is_anomalous=False,
                confidence="low",
                signals=signals,
            ),
            data_quality,
        )

    score = _weighted_score(component_scores)
    severity = severity_for_score(score)
    return (
        AnomalyResult(
            status="ok",
            score=score,
            severity=severity,
            is_anomalous=severity in {"moderate", "high", "extreme"},
            confidence=_confidence(
                level_sample_size=level_sample_size,
                level_years_used=level_years_used,
                change_reference=change_reference,
                component_count=len(component_scores),
                data_quality_status=data_quality_status,
            ),
            signals=signals,
        ),
        data_quality,
    )


def percentile_to_anomaly_score(percentile: float) -> int:
    return round(abs(percentile - 50) * 2)


def severity_for_score(score: int) -> str:
    if score >= 95:
        return "extreme"
    if score >= 80:
        return "high"
    if score >= 60:
        return "moderate"
    if score >= 30:
        return "low"
    return "normal"


def _weighted_score(component_scores: list[tuple[float, int]]) -> int:
    total_weight = sum(weight for weight, _score in component_scores)
    return round(sum(weight * score for weight, score in component_scores) / total_weight)


def _confidence(
    *,
    level_sample_size: int,
    level_years_used: int,
    change_reference: ChangeReference,
    component_count: int,
    data_quality_status: str,
) -> str:
    if data_quality_status != "normal":
        return "low"
    if component_count < 2:
        return "medium"
    if (
        level_sample_size >= 150
        and level_years_used >= 10
        and change_reference.sample_size >= DELTA_HIGH_CONFIDENCE_SAMPLE_SIZE
        and change_reference.years_used >= DELTA_HIGH_CONFIDENCE_YEARS
    ):
        return "high"
    if (
        level_sample_size >= 75
        and level_years_used >= 5
        and change_reference.sample_size >= DELTA_MIN_SAMPLE_SIZE
        and change_reference.years_used >= DELTA_MIN_YEARS
    ):
        return "medium"
    return "low"


def _nearest_measurement(
    measurements: list[Measurement],
    *,
    target: datetime,
    tolerance: timedelta,
) -> Measurement | None:
    candidates = [
        measurement
        for measurement in measurements
        if abs(measurement.measured_at - target) <= tolerance
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda measurement: (abs(measurement.measured_at - target), measurement.measured_at),
    )


def _largest_gap_minutes(measurements: list[Measurement]) -> float | None:
    if len(measurements) < 2:
        return None
    gaps = [
        (current.measured_at - previous.measured_at).total_seconds() / 60
        for previous, current in zip(measurements, measurements[1:], strict=False)
    ]
    return max(gaps)


def _has_large_gap(measurements: list[Measurement]) -> bool:
    if len(measurements) < 4:
        return False
    gaps = [
        (current.measured_at - previous.measured_at).total_seconds() / 60
        for previous, current in zip(measurements, measurements[1:], strict=False)
    ]
    return max(gaps) > median(gaps) * 2


def _is_flatline(measurements: list[Measurement]) -> bool:
    recent = measurements[-12:]
    if len(recent) < 12:
        return False
    values = [measurement.value for measurement in recent]
    return max(values) - min(values) <= 0.005


def _has_isolated_latest_spike(measurements: list[Measurement]) -> bool:
    if len(measurements) < 4:
        return False
    previous_values = [measurement.value for measurement in measurements[-4:-1]]
    latest = measurements[-1].value
    spread = max(previous_values) - min(previous_values)
    baseline = median(previous_values)
    return abs(latest - baseline) >= max(1.0, spread * 5)


def _quality_signal(
    signal_type: str,
    message: str,
    *,
    value: float | None = None,
    unit: str | None = None,
) -> AnomalySignal:
    return AnomalySignal(
        type=signal_type,
        category="data_quality",
        score=None,
        direction=None,
        value=value,
        unit=unit,
        percentile=None,
        message=message,
    )


def _level_message(percentile: float) -> str:
    if percentile >= 50:
        return (
            f"Water level is higher than {percentile:.0f}% of historical observations "
            "for this time of year."
        )
    return (
        f"Water level is lower than {100 - percentile:.0f}% of historical observations "
        "for this time of year."
    )


def _change_message(delta: float, percentile: float) -> str:
    direction = "rise" if delta >= 0 else "fall"
    comparable = percentile if percentile >= 50 else 100 - percentile
    return (
        f"The 24-hour {direction} is larger than {comparable:.0f}% of historical "
        "24-hour changes for this time of year."
    )
