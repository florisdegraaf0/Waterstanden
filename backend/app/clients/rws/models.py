from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RwsLatestObservation:
    code: str
    name: str
    latitude: float
    longitude: float
    value: float | None
    unit_code: str | None
    measured_at: datetime | None
    parameter_description: str
    status: str | None
    quality_code: str | None
    grootheid_code: str
    compartiment_code: str
    hoedanigheid_code: str | None
    raw_metadata: dict[str, str | float | None]

