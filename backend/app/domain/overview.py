from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OverviewPrimarySignal:
    type: str
    direction: str | None
    value: float | None
    unit: str | None
    percentile: float | None
    score: int | None
    message: str


@dataclass(frozen=True)
class OverviewStation:
    station_id: str
    station_name: str
    water_system: str
    latitude: float
    longitude: float
    current_value: float | None
    unit: str | None
    measured_at: datetime | None
    parameter: str
    seasonal_percentile: float | None
    seasonal_status: str
    anomaly_score: int | None
    anomaly_severity: str
    anomaly_status: str
    anomaly_direction: str | None
    confidence: str
    data_quality_status: str
    freshness_status: str
    is_rankable: bool
    delta_24h: float | None
    primary_signal: OverviewPrimarySignal | None
    historical_years: int
    historical_sample_size: int
    recent_measurement_count: int


@dataclass(frozen=True)
class OverviewSummary:
    stations_monitored: int
    high_or_extreme_anomalies: int
    extreme_anomalies: int
    rapidly_rising: int
    rapidly_falling: int
    data_limited_or_stale: int


@dataclass(frozen=True)
class OverviewCoverage:
    historical_context_stations: int
    insufficient_data_stations: int
    stale_stations: int
    rankable_stations: int


@dataclass(frozen=True)
class OverviewResult:
    generated_at: datetime
    summary: OverviewSummary
    coverage: OverviewCoverage
    stations: list[OverviewStation]
