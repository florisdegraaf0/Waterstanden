from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    latitude: float
    longitude: float
    latest_value: float | None
    unit: str | None
    measured_at: datetime | None
    parameter: str
    status: str | None
    quality_code: str | None
    metadata: dict[str, str | float | None]


@dataclass(frozen=True)
class Measurement:
    measured_at: datetime
    value: float
    unit: str
    parameter: str
    quality_code: str | None = None
    source_station_code: str | None = None
    source_unit: str | None = None
    source_metadata: dict[str, str | float | None] | None = None


@dataclass(frozen=True)
class DailyStatistic:
    date: date
    value: float
    min_value: float
    max_value: float
    mean_value: float
    median_value: float
    observation_count: int


@dataclass(frozen=True)
class HistoricalChangeStatistic:
    date: date
    window_hours: int
    delta_value: float
    observation_count: int


@dataclass(frozen=True)
class ReferencePeriod:
    window_days: int
    first_year: int | None
    last_year: int | None


@dataclass(frozen=True)
class PercentileReferenceValues:
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float


@dataclass(frozen=True)
class SeasonalContext:
    status: str
    percentile: float | None
    sample_size: int
    years_used: int
    historical_sample_size: int
    historical_years: int
    reference_period: ReferencePeriod
    reference_values: PercentileReferenceValues | None


@dataclass(frozen=True)
class AnomalySignal:
    type: str
    category: str
    score: int | None
    direction: str | None
    value: float | None
    unit: str | None
    percentile: float | None
    message: str


@dataclass(frozen=True)
class AnomalyDataQuality:
    status: str
    signals: list[AnomalySignal]
    historical_years: int
    historical_sample_size: int
    recent_measurement_count: int
    largest_recent_gap_minutes: float | None


@dataclass(frozen=True)
class AnomalyResult:
    status: str
    score: int | None
    severity: str
    is_anomalous: bool
    confidence: str
    signals: list[AnomalySignal]


@dataclass(frozen=True)
class StationAnomaly:
    station_id: str
    parameter: str
    evaluated_at: datetime
    current: Measurement
    anomaly: AnomalyResult
    data_quality: AnomalyDataQuality
