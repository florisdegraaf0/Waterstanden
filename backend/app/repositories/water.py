from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from statistics import mean, median

from geoalchemy2 import WKTElement
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.base import (
    MeasurementRecord,
    StationDailyStatisticRecord,
    StationRecord,
)
from app.domain.models import DailyStatistic, Measurement, Station


class WaterRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert_station(self, station: Station) -> int:
        statement = (
            insert(StationRecord)
            .values(
                external_id=station.id,
                name=station.name,
                location=WKTElement(f"POINT({station.longitude} {station.latitude})", srid=4326),
                station_metadata=station.metadata,
            )
            .on_conflict_do_update(
                index_elements=[StationRecord.external_id],
                set_={
                    "name": station.name,
                    "location": WKTElement(
                        f"POINT({station.longitude} {station.latitude})",
                        srid=4326,
                    ),
                    "metadata": station.metadata,
                    "updated_at": datetime.now().astimezone(),
                },
            )
            .returning(StationRecord.id)
        )
        return self._db.execute(statement).scalar_one()

    def get_station_record_id(self, external_id: str) -> int | None:
        return self._db.scalar(
            select(StationRecord.id).where(StationRecord.external_id == external_id)
        )

    def delete_stations_not_in(self, active_external_ids: set[str]) -> int:
        statement = delete(StationRecord)
        if active_external_ids:
            statement = statement.where(StationRecord.external_id.not_in(active_external_ids))
        result = self._db.execute(statement)
        return result.rowcount or 0

    def upsert_measurements(self, station_record_id: int, measurements: list[Measurement]) -> int:
        if not measurements:
            return 0

        rows = [
            {
                "station_id": station_record_id,
                "measured_at": measurement.measured_at,
                "value": measurement.value,
                "unit": measurement.unit,
                "parameter": measurement.parameter,
                "quality_code": measurement.quality_code,
                "source_station_code": measurement.source_station_code,
                "source_unit": measurement.source_unit,
                "source_metadata": measurement.source_metadata or {},
            }
            for measurement in measurements
        ]
        statement = insert(MeasurementRecord).values(rows)
        upsert = statement.on_conflict_do_update(
            constraint="uq_measurement_series_time",
            set_={
                "value": statement.excluded.value,
                "unit": statement.excluded.unit,
                "quality_code": statement.excluded.quality_code,
                "source_station_code": statement.excluded.source_station_code,
                "source_unit": statement.excluded.source_unit,
                "source_metadata": statement.excluded.source_metadata,
                "updated_at": datetime.now().astimezone(),
            },
        )
        result = self._db.execute(upsert)
        return result.rowcount or 0

    def recompute_daily_statistics(
        self,
        *,
        station_record_id: int,
        parameter: str,
        start_date: date,
        end_date: date,
    ) -> int:
        measurements = self._db.scalars(
            select(MeasurementRecord)
            .where(MeasurementRecord.station_id == station_record_id)
            .where(MeasurementRecord.parameter == parameter)
            .where(
                MeasurementRecord.measured_at
                >= datetime.combine(start_date, datetime.min.time())
            )
            .where(MeasurementRecord.measured_at < datetime.combine(end_date, datetime.min.time()))
            .order_by(MeasurementRecord.measured_at)
        ).all()

        by_date: dict[date, list[MeasurementRecord]] = defaultdict(list)
        for measurement in measurements:
            by_date[measurement.measured_at.date()].append(measurement)

        affected = 0
        for day, day_measurements in by_date.items():
            values = [measurement.value for measurement in day_measurements]
            source_metadata = _merge_daily_source_metadata(day_measurements)
            statement = (
                insert(StationDailyStatisticRecord)
                .values(
                    station_id=station_record_id,
                    date=day,
                    parameter=parameter,
                    min_value=min(values),
                    max_value=max(values),
                    mean_value=mean(values),
                    median_value=median(values),
                    observation_count=len(values),
                    source_metadata=source_metadata,
                )
                .on_conflict_do_update(
                    constraint="uq_station_daily_statistics_series_date",
                    set_={
                        "min_value": min(values),
                        "max_value": max(values),
                        "mean_value": mean(values),
                        "median_value": median(values),
                        "observation_count": len(values),
                        "source_metadata": source_metadata,
                        "updated_at": datetime.now().astimezone(),
                    },
                )
            )
            self._db.execute(statement)
            affected += 1
        return affected

    def list_daily_statistics(
        self,
        station_external_id: str,
        parameter: str,
    ) -> list[DailyStatistic]:
        station_record_id = self.get_station_record_id(station_external_id)
        if station_record_id is None:
            return []

        rows = self._db.scalars(
            select(StationDailyStatisticRecord)
            .where(StationDailyStatisticRecord.station_id == station_record_id)
            .where(StationDailyStatisticRecord.parameter == parameter)
            .order_by(StationDailyStatisticRecord.date)
        ).all()
        return [
            DailyStatistic(
                date=row.date,
                value=row.median_value,
                min_value=row.min_value,
                max_value=row.max_value,
                mean_value=row.mean_value,
                median_value=row.median_value,
                observation_count=row.observation_count,
            )
            for row in rows
        ]


def _merge_daily_source_metadata(
    measurements: list[MeasurementRecord],
) -> dict[str, str | int | None]:
    first = measurements[0]
    return {
        "source_station_code": first.source_station_code,
        "source_unit": first.source_unit,
        "observation_count": len(measurements),
    }
