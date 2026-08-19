from datetime import datetime

from pydantic import BaseModel, Field


class StationSummary(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    latest_value: float | None = None
    unit: str | None = None
    measured_at: datetime | None = None
    parameter: str
    status: str | None = None
    quality_code: str | None = None


class StationDetail(StationSummary):
    metadata: dict[str, str | float | None] = Field(default_factory=dict)


class MeasurementPoint(BaseModel):
    measured_at: datetime
    value: float
    unit: str
    parameter: str
    quality_code: str | None = None


class CurrentMeasurement(BaseModel):
    value: float | None
    unit: str | None
    measured_at: datetime | None


class SeasonalReferencePeriod(BaseModel):
    window_days: int
    first_year: int | None
    last_year: int | None


class SeasonalReferenceValues(BaseModel):
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float


class SeasonalContextPayload(BaseModel):
    percentile: float | None
    status: str
    sample_size: int
    years_used: int
    historical_sample_size: int
    historical_years: int
    reference_period: SeasonalReferencePeriod
    reference_values: SeasonalReferenceValues | None = None


class StationSeasonalContext(BaseModel):
    station_id: str
    parameter: str
    current: CurrentMeasurement
    seasonal_context: SeasonalContextPayload


class AnomalySignalPayload(BaseModel):
    type: str
    category: str
    score: int | None = None
    direction: str | None = None
    value: float | None = None
    unit: str | None = None
    percentile: float | None = None
    message: str


class AnomalyResultPayload(BaseModel):
    status: str
    score: int | None = None
    severity: str
    is_anomalous: bool
    confidence: str
    signals: list[AnomalySignalPayload]


class AnomalyDataQualityPayload(BaseModel):
    status: str
    signals: list[AnomalySignalPayload]
    historical_years: int
    historical_sample_size: int
    recent_measurement_count: int
    largest_recent_gap_minutes: float | None = None


class StationAnomalyPayload(BaseModel):
    station_id: str
    parameter: str
    evaluated_at: datetime
    current: CurrentMeasurement
    anomaly: AnomalyResultPayload
    data_quality: AnomalyDataQualityPayload


class OverviewPrimarySignalPayload(BaseModel):
    type: str
    direction: str | None = None
    value: float | None = None
    unit: str | None = None
    percentile: float | None = None
    score: int | None = None
    message: str


class OverviewStationPayload(BaseModel):
    station_id: str
    station_name: str
    water_system: str
    latitude: float
    longitude: float
    current_value: float | None = None
    unit: str | None = None
    measured_at: datetime | None = None
    parameter: str
    seasonal_percentile: float | None = None
    seasonal_status: str
    anomaly_score: int | None = None
    anomaly_severity: str
    anomaly_status: str
    anomaly_direction: str | None = None
    confidence: str
    data_quality_status: str
    freshness_status: str
    delta_24h: float | None = None
    primary_signal: OverviewPrimarySignalPayload | None = None


class OverviewSummaryPayload(BaseModel):
    stations_monitored: int
    high_or_extreme_anomalies: int
    extreme_anomalies: int
    rapidly_rising: int
    rapidly_falling: int
    data_limited_or_stale: int


class OverviewCoveragePayload(BaseModel):
    historical_context_stations: int
    insufficient_data_stations: int
    stale_stations: int
    rankable_stations: int


class OverviewPayload(BaseModel):
    generated_at: datetime
    summary: OverviewSummaryPayload
    coverage: OverviewCoveragePayload
    stations: list[OverviewStationPayload]
