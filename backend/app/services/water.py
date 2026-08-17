import logging
from datetime import UTC, datetime, timedelta

from app.clients.rws.client import RwsClient
from app.clients.rws.parsers import normalize_latest_water_level
from app.domain.models import Measurement, Station
from app.exceptions import ExternalServiceError, StationNotFound

logger = logging.getLogger(__name__)


class WaterService:
    def __init__(
        self,
        rws_client: RwsClient,
        use_fallback_measurements: bool = True,
        active_station_max_age: timedelta = timedelta(hours=24),
        now: datetime | None = None,
    ) -> None:
        self._rws_client = rws_client
        self._use_fallback_measurements = use_fallback_measurements
        self._active_station_max_age = active_station_max_age
        self._now = now

    async def list_stations(self) -> list[Station]:
        observations = await self._rws_client.fetch_latest_water_level_locations()
        stations: list[Station] = []
        seen: set[str] = set()
        now = self._now or datetime.now(UTC)

        for observation in observations:
            if observation.code in seen:
                continue
            latest = normalize_latest_water_level(observation)
            if latest is None:
                continue
            if latest.measured_at < now - self._active_station_max_age:
                continue

            seen.add(observation.code)
            stations.append(
                Station(
                    id=observation.code,
                    name=observation.name,
                    latitude=observation.latitude,
                    longitude=observation.longitude,
                    latest_value=latest.value,
                    unit=latest.unit,
                    measured_at=latest.measured_at,
                    parameter="water_level",
                    status=observation.status,
                    quality_code=observation.quality_code,
                    metadata=observation.raw_metadata,
                )
            )

        return sorted(stations, key=lambda station: station.name.lower())

    async def get_station(self, station_id: str) -> Station:
        for station in await self.list_stations():
            if station.id == station_id:
                return station
        raise StationNotFound(f"Station {station_id!r} was not found")

    async def get_measurements(self, station_id: str, hours: int) -> list[Measurement]:
        try:
            measurements = await self._rws_client.fetch_recent_measurements(station_id, hours)
        except ExternalServiceError:
            if not self._use_fallback_measurements:
                raise
            logger.info(
                "Using fallback recent measurements",
                extra={"station_id": station_id, "hours": hours},
            )
            measurements = _fallback_measurements(hours)

        return measurements


def _fallback_measurements(hours: int) -> list[Measurement]:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=min(hours, 48))
    points: list[Measurement] = []
    current = start
    index = 0
    while current <= now:
        points.append(
            Measurement(
                measured_at=current,
                value=1.15 + (index % 12) * 0.025,
                unit="m NAP",
                parameter="water_level",
                quality_code="fallback",
            )
        )
        current += timedelta(hours=1)
        index += 1
    return points
