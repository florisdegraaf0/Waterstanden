from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean, median

from app.clients.rws.client import RwsClient
from app.clients.rws.parsers import normalize_latest_water_level
from app.config import get_settings
from app.domain.curated_stations import CURATED_STATION_BY_ID, CURATED_STATIONS
from app.domain.models import DailyStatistic, HistoricalChangeStatistic, Measurement, Station
from app.domain.parameters import validate_parameter
from app.services.water import WaterService

logger = logging.getLogger(__name__)


async def run_backfill(
    *,
    station_id: str,
    parameter: str,
    start_date: date,
    end_date: date,
) -> None:
    parameter = validate_parameter(parameter)
    settings = get_settings()
    client = RwsClient(settings)
    try:
        from app.db.session import SessionLocal
        from app.repositories.water import WaterRepository

        station = await _get_station_for_backfill(client, station_id)
        with SessionLocal() as db:
            repository = WaterRepository(db)
            station_record_id = repository.upsert_station(station)
            db.commit()

            for chunk_start, chunk_end in _year_chunks(start_date, end_date):
                logger.info(
                    "Fetching historical RWS measurements",
                    extra={
                        "station_id": station_id,
                        "parameter": parameter,
                        "from": chunk_start.isoformat(),
                        "to": chunk_end.isoformat(),
                    },
                )
                measurements = await client.fetch_historical_measurements(
                    station_id,
                    datetime.combine(chunk_start, time.min, tzinfo=UTC),
                    datetime.combine(chunk_end + timedelta(days=1), time.min, tzinfo=UTC),
                    parameter=parameter,
                )
                measurements = [
                    measurement
                    for measurement in measurements
                    if measurement.parameter == parameter
                    and _is_selected_historical_series(
                        parameter,
                        measurement.source_metadata or {},
                    )
                ]
                raw_count = repository.upsert_measurements(
                    station_record_id,
                    measurements,
                )
                daily_statistics = _daily_statistics_from_measurements(measurements)
                daily_count = repository.upsert_daily_statistics(
                    station_record_id=station_record_id,
                    parameter=parameter,
                    daily_statistics=daily_statistics,
                )
                change_count = repository.upsert_historical_change_statistics(
                    station_record_id=station_record_id,
                    parameter=parameter,
                    change_statistics=_daily_change_statistics_from_daily_statistics(
                        daily_statistics,
                        window_hours=24,
                    ),
                )
                db.commit()
                logger.info(
                    "Stored historical RWS measurements",
                    extra={
                        "station_id": station_id,
                        "measurements_seen": len(measurements),
                        "raw_measurements": raw_count,
                        "daily_statistics": daily_count,
                        "change_statistics": change_count,
                    },
                )
    finally:
        await client.close()


async def _get_station_for_backfill(client: RwsClient, station_id: str) -> Station:
    service = WaterService(client, use_fallback_measurements=False)
    try:
        return await service.get_station(station_id)
    except Exception:
        station = await _get_curated_station_from_latest_feed(client, station_id)
        if station is not None:
            logger.warning(
                "Using stale latest station metadata for historical backfill",
                extra={"station_id": station_id},
            )
            return station
        if station_id != "lobith.bovenrijn.tolkamer":
            raise
        logger.warning("Using built-in Lobith station metadata for backfill")
        return Station(
            id="lobith.bovenrijn.tolkamer",
            name="Lobith, Bovenrijn, Tolkamer",
            latitude=51.8495,
            longitude=6.1024,
            latest_value=None,
            unit="m NAP",
            measured_at=None,
            parameter="water_level",
            status=None,
            quality_code=None,
            metadata={"source": "built_in_lobith_backfill_metadata"},
        )


async def _get_curated_station_from_latest_feed(
    client: RwsClient,
    station_id: str,
) -> Station | None:
    curated = CURATED_STATION_BY_ID.get(station_id)
    if curated is None:
        return None

    for observation in await client.fetch_latest_water_level_locations():
        if observation.code != station_id:
            continue
        latest = normalize_latest_water_level(observation)
        return Station(
            id=observation.code,
            name=curated.display_name,
            latitude=observation.latitude,
            longitude=observation.longitude,
            latest_value=latest.value if latest else None,
            unit=latest.unit if latest else None,
            measured_at=latest.measured_at if latest else None,
            parameter="water_level",
            status=observation.status,
            quality_code=observation.quality_code,
            metadata={
                **observation.raw_metadata,
                "rws_name": observation.name,
                "water_system": curated.water_system,
                "significance": curated.significance,
                "sort_order": curated.sort_order,
                "source": "stale_latest_feed_backfill_metadata",
            },
        )
    return None


def _year_chunks(start_date: date, end_date: date) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = start_date
    while current <= end_date:
        chunk_end = min(date(current.year, 12, 31), end_date)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _is_selected_lobith_series(source_metadata: dict[str, object]) -> bool:
    return _is_selected_historical_series("water_level", source_metadata)


def _is_selected_historical_series(
    parameter: str,
    source_metadata: dict[str, object],
) -> bool:
    if source_metadata.get("station_code") != "lobith.bovenrijn.tolkamer":
        return True
    if parameter == "discharge":
        return (
            source_metadata.get("unit") == "m3/s"
            and source_metadata.get("grootheid") == "Q"
            and source_metadata.get("proces_type") == "meting"
        )
    return (
        source_metadata.get("hoedanigheid") == "NAP"
        and source_metadata.get("proces_type") == "meting"
        and source_metadata.get("meetapparaat") == "10042"
    )


def _daily_statistics_from_measurements(measurements: list[Measurement]) -> list[DailyStatistic]:
    by_date: dict[date, list[Measurement]] = defaultdict(list)
    for measurement in measurements:
        by_date[measurement.measured_at.date()].append(measurement)

    daily_statistics: list[DailyStatistic] = []
    for day, day_measurements in sorted(by_date.items()):
        values = [measurement.value for measurement in day_measurements]
        daily_statistics.append(
            DailyStatistic(
                date=day,
                value=median(values),
                min_value=min(values),
                max_value=max(values),
                mean_value=mean(values),
                median_value=median(values),
                observation_count=len(values),
            )
        )
    return daily_statistics


def _daily_change_statistics_from_daily_statistics(
    daily_statistics: list[DailyStatistic],
    *,
    window_hours: int,
) -> list[HistoricalChangeStatistic]:
    if window_hours != 24:
        raise ValueError("Only 24 hour daily change statistics are supported")

    by_date = {statistic.date: statistic for statistic in daily_statistics}
    changes: list[HistoricalChangeStatistic] = []
    for statistic in sorted(daily_statistics, key=lambda value: value.date):
        previous = by_date.get(statistic.date - timedelta(days=1))
        if previous is None:
            continue
        changes.append(
            HistoricalChangeStatistic(
                date=statistic.date,
                window_hours=window_hours,
                delta_value=statistic.mean_value - previous.mean_value,
                observation_count=statistic.observation_count + previous.observation_count,
            )
        )
    return changes


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill historical RWS station measurements.")
    parser.add_argument("--station-id")
    parser.add_argument(
        "--top-stations",
        action="store_true",
        help="Backfill all curated top-25 stations.",
    )
    parser.add_argument("--parameter", default="water_level")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    args = parser.parse_args()
    if not args.station_id and not args.top_stations:
        parser.error("--station-id is required unless --top-stations is set")
    return args


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    station_ids = (
        [station.id for station in CURATED_STATIONS]
        if args.top_stations
        else [args.station_id]
    )
    for station_id in station_ids:
        asyncio.run(
            run_backfill(
                station_id=station_id,
                parameter=args.parameter,
                start_date=date.fromisoformat(args.from_date),
                end_date=date.fromisoformat(args.to_date),
            )
        )


if __name__ == "__main__":
    main()
