import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.clients.rws.client import RwsClient
from app.clients.rws.parsers import normalize_latest_water_level
from app.domain.curated_stations import CURATED_STATION_BY_ID, CURATED_STATION_IDS
from app.domain.models import Measurement, Station
from app.exceptions import ExternalServiceError, StationNotFound

logger = logging.getLogger(__name__)


class WaterService:
    def __init__(
        self,
        rws_client: RwsClient,
        use_fallback_measurements: bool = True,
        active_station_max_age_hours: int = 24,
        active_station_recent_check_concurrency: int = 10,
        active_station_verify_recent_measurements: bool = False,
        now: datetime | None = None,
    ) -> None:
        self._rws_client = rws_client
        self._use_fallback_measurements = use_fallback_measurements
        self._active_station_max_age = timedelta(hours=active_station_max_age_hours)
        self._active_station_recent_check_concurrency = active_station_recent_check_concurrency
        self._active_station_verify_recent_measurements = active_station_verify_recent_measurements
        self._now = now

    async def list_stations(self) -> list[Station]:
        observations = await self._rws_client.fetch_latest_water_level_locations()
        candidates: list[Station] = []
        seen: set[str] = set()
        now = self._now or datetime.now(UTC)
        cutoff = now - self._active_station_max_age

        for observation in observations:
            curated = CURATED_STATION_BY_ID.get(observation.code)
            if curated is None:
                continue
            if observation.code in seen:
                continue
            latest = normalize_latest_water_level(observation)
            if latest is None:
                continue
            if latest.measured_at < cutoff:
                continue

            seen.add(observation.code)
            candidates.append(
                Station(
                    id=observation.code,
                    name=curated.display_name,
                    latitude=observation.latitude,
                    longitude=observation.longitude,
                    latest_value=latest.value,
                    unit=latest.unit,
                    measured_at=latest.measured_at,
                    parameter="water_level",
                    status=observation.status,
                    quality_code=observation.quality_code,
                    metadata={
                        **observation.raw_metadata,
                        "rws_name": observation.name,
                        "water_system": curated.water_system,
                        "significance": curated.significance,
                        "sort_order": curated.sort_order,
                    },
                )
            )

        stations = (
            await self._filter_stations_with_recent_measurements(candidates, cutoff)
            if self._active_station_verify_recent_measurements
            else candidates
        )
        return sorted(
            stations,
            key=lambda station: CURATED_STATION_BY_ID[station.id].sort_order,
        )

    async def get_station(self, station_id: str) -> Station:
        for station in await self.list_stations():
            if station.id == station_id:
                return station
        raise StationNotFound(f"Station {station_id!r} was not found")

    async def get_measurements(self, station_id: str, hours: int) -> list[Measurement]:
        if station_id not in CURATED_STATION_IDS:
            raise StationNotFound(f"Station {station_id!r} was not found")

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

    async def _filter_stations_with_recent_measurements(
        self,
        stations: list[Station],
        cutoff: datetime,
    ) -> list[Station]:
        semaphore = asyncio.Semaphore(self._active_station_recent_check_concurrency)

        async def is_active(station: Station) -> bool:
            async with semaphore:
                try:
                    measurements = await self._rws_client.fetch_recent_measurements(
                        station.id,
                        int(self._active_station_max_age.total_seconds() // 3600),
                    )
                except ExternalServiceError:
                    logger.info(
                        "Skipping station without recent RWS measurements",
                        extra={"station_id": station.id},
                    )
                    return False
                return any(measurement.measured_at >= cutoff for measurement in measurements)

        checks = await asyncio.gather(*(is_active(station) for station in stations))
        return [station for station, active in zip(stations, checks, strict=True) if active]


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
