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
    reference_period: ReferencePeriod
    reference_values: PercentileReferenceValues | None
