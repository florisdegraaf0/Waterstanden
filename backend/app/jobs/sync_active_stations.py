from __future__ import annotations

import argparse
import asyncio
import logging

from app.clients.rws.client import RwsClient
from app.config import get_settings
from app.db.session import SessionLocal
from app.repositories.water import WaterRepository
from app.services.water import WaterService

logger = logging.getLogger(__name__)


async def sync_active_stations(active_station_max_age_hours: int | None = None) -> None:
    settings = get_settings()
    max_age_hours = active_station_max_age_hours or settings.active_station_max_age_hours
    client = RwsClient(settings)
    try:
        stations = await WaterService(
            client,
            active_station_max_age_hours=max_age_hours,
            active_station_recent_check_concurrency=settings.active_station_recent_check_concurrency,
            active_station_verify_recent_measurements=True,
        ).list_stations()
        active_ids = {station.id for station in stations}
        with SessionLocal() as db:
            repository = WaterRepository(db)
            for station in stations:
                repository.upsert_station(station)
            deleted = repository.delete_stations_not_in(active_ids)
            db.commit()
        logger.info(
            "Synchronized active stations",
            extra={"active_stations": len(active_ids), "deleted_inactive_stations": deleted},
        )
    finally:
        await client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync active RWS stations and remove inactive station records."
    )
    parser.add_argument("--active-max-age-hours", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    asyncio.run(sync_active_stations(args.active_max_age_hours))


if __name__ == "__main__":
    main()
