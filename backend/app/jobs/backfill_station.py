from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta

from app.clients.rws.client import RwsClient
from app.config import get_settings
from app.db.session import SessionLocal
from app.domain.models import Station
from app.repositories.water import WaterRepository
from app.services.water import WaterService

logger = logging.getLogger(__name__)


async def run_backfill(
    *,
    station_id: str,
    parameter: str,
    start_date: date,
    end_date: date,
) -> None:
    settings = get_settings()
    client = RwsClient(settings)
    try:
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
                )
                measurements = [
                    measurement
                    for measurement in measurements
                    if measurement.parameter == parameter
                    and _is_selected_lobith_series(measurement.source_metadata or {})
                ]
                upserted = repository.upsert_measurements(station_record_id, measurements)
                daily_count = repository.recompute_daily_statistics(
                    station_record_id=station_record_id,
                    parameter=parameter,
                    start_date=chunk_start,
                    end_date=chunk_end + timedelta(days=1),
                )
                db.commit()
                logger.info(
                    "Stored historical RWS measurements",
                    extra={
                        "station_id": station_id,
                        "measurements_seen": len(measurements),
                        "measurements_upserted": upserted,
                        "daily_statistics": daily_count,
                    },
                )
    finally:
        await client.close()


async def _get_station_for_backfill(client: RwsClient, station_id: str) -> Station:
    service = WaterService(client, use_fallback_measurements=False)
    try:
        return await service.get_station(station_id)
    except Exception:
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


def _year_chunks(start_date: date, end_date: date) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = start_date
    while current <= end_date:
        chunk_end = min(date(current.year, 12, 31), end_date)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _is_selected_lobith_series(source_metadata: dict[str, object]) -> bool:
    if source_metadata.get("station_code") != "lobith.bovenrijn.tolkamer":
        return True
    return (
        source_metadata.get("hoedanigheid") == "NAP"
        and source_metadata.get("proces_type") == "meting"
        and source_metadata.get("meetapparaat") == "10042"
        and source_metadata.get("waardebepalingsmethode") == "other:F007"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill historical RWS station measurements.")
    parser.add_argument("--station-id", required=True)
    parser.add_argument("--parameter", default="water_level")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    asyncio.run(
        run_backfill(
            station_id=args.station_id,
            parameter=args.parameter,
            start_date=date.fromisoformat(args.from_date),
            end_date=date.fromisoformat(args.to_date),
        )
    )


if __name__ == "__main__":
    main()
