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
    reference_period: SeasonalReferencePeriod
    reference_values: SeasonalReferenceValues | None = None


class StationSeasonalContext(BaseModel):
    station_id: str
    parameter: str
    current: CurrentMeasurement
    seasonal_context: SeasonalContextPayload
