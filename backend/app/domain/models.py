from dataclasses import dataclass
from datetime import datetime


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

