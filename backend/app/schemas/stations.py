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

