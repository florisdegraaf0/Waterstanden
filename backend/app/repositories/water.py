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
    StationHistoricalChangeStatisticRecord,
    StationOverviewSnapshotRecord,
    StationRecord,
)
from app.domain.models import DailyStatistic, HistoricalChangeStatistic, Measurement, Station
from app.domain.overview import OverviewPrimarySignal, OverviewStation

_MEASUREMENT_UPSERT_BATCH_SIZE = 100


class WaterRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

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

        affected = 0
        rows = _measurement_rows(station_record_id, measurements)
        for batch in _chunks(rows, _MEASUREMENT_UPSERT_BATCH_SIZE):
            statement = insert(MeasurementRecord).values(batch)
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
            affected += result.rowcount or 0
        return affected

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

    def upsert_daily_statistics(
        self,
        *,
        station_record_id: int,
        parameter: str,
        daily_statistics: list[DailyStatistic],
    ) -> int:
        affected = 0
        for statistic in daily_statistics:
            statement = (
                insert(StationDailyStatisticRecord)
                .values(
                    station_id=station_record_id,
                    date=statistic.date,
                    parameter=parameter,
                    min_value=statistic.min_value,
                    max_value=statistic.max_value,
                    mean_value=statistic.mean_value,
                    median_value=statistic.median_value,
                    observation_count=statistic.observation_count,
                    source_metadata={
                        "source": "historical_backfill_daily_aggregation",
                        "raw_observation_count": statistic.observation_count,
                    },
                )
                .on_conflict_do_update(
                    constraint="uq_station_daily_statistics_series_date",
                    set_={
                        "min_value": statistic.min_value,
                        "max_value": statistic.max_value,
                        "mean_value": statistic.mean_value,
                        "median_value": statistic.median_value,
                        "observation_count": statistic.observation_count,
                        "source_metadata": {
                            "source": "historical_backfill_daily_aggregation",
                            "raw_observation_count": statistic.observation_count,
                        },
                        "updated_at": datetime.now().astimezone(),
                    },
                )
            )
            result = self._db.execute(statement)
            affected += result.rowcount or 0
        return affected

    def upsert_historical_change_statistics(
        self,
        *,
        station_record_id: int,
        parameter: str,
        change_statistics: list[HistoricalChangeStatistic],
    ) -> int:
        affected = 0
        for statistic in change_statistics:
            statement = (
                insert(StationHistoricalChangeStatisticRecord)
                .values(
                    station_id=station_record_id,
                    date=statistic.date,
                    parameter=parameter,
                    window_hours=statistic.window_hours,
                    delta_value=statistic.delta_value,
                    observation_count=statistic.observation_count,
                    source_metadata={
                        "source": "historical_backfill_daily_mean_delta",
                    },
                )
                .on_conflict_do_update(
                    constraint="uq_station_historical_change_statistics_series_date",
                    set_={
                        "delta_value": statistic.delta_value,
                        "observation_count": statistic.observation_count,
                        "source_metadata": {
                            "source": "historical_backfill_daily_mean_delta",
                        },
                        "updated_at": datetime.now().astimezone(),
                    },
                )
            )
            result = self._db.execute(statement)
            affected += result.rowcount or 0
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

    def list_daily_statistics_for_stations(
        self,
        station_external_ids: list[str],
        parameter: str,
    ) -> dict[str, list[DailyStatistic]]:
        if not station_external_ids:
            return {}

        rows = self._db.execute(
            select(StationRecord.external_id, StationDailyStatisticRecord)
            .join(
                StationDailyStatisticRecord,
                StationDailyStatisticRecord.station_id == StationRecord.id,
            )
            .where(StationRecord.external_id.in_(station_external_ids))
            .where(StationDailyStatisticRecord.parameter == parameter)
            .order_by(StationRecord.external_id, StationDailyStatisticRecord.date)
        ).all()
        grouped: dict[str, list[DailyStatistic]] = defaultdict(list)
        for external_id, row in rows:
            grouped[external_id].append(
                DailyStatistic(
                    date=row.date,
                    value=row.median_value,
                    min_value=row.min_value,
                    max_value=row.max_value,
                    mean_value=row.mean_value,
                    median_value=row.median_value,
                    observation_count=row.observation_count,
                )
            )
        return grouped

    def list_historical_change_statistics(
        self,
        station_external_id: str,
        parameter: str,
        window_hours: int,
    ) -> list[HistoricalChangeStatistic]:
        station_record_id = self.get_station_record_id(station_external_id)
        if station_record_id is None:
            return []

        rows = self._db.scalars(
            select(StationHistoricalChangeStatisticRecord)
            .where(StationHistoricalChangeStatisticRecord.station_id == station_record_id)
            .where(StationHistoricalChangeStatisticRecord.parameter == parameter)
            .where(StationHistoricalChangeStatisticRecord.window_hours == window_hours)
            .order_by(StationHistoricalChangeStatisticRecord.date)
        ).all()
        return [
            HistoricalChangeStatistic(
                date=row.date,
                window_hours=row.window_hours,
                delta_value=row.delta_value,
                observation_count=row.observation_count,
            )
            for row in rows
        ]

    def list_historical_change_statistics_for_stations(
        self,
        station_external_ids: list[str],
        parameter: str,
        window_hours: int,
    ) -> dict[str, list[HistoricalChangeStatistic]]:
        if not station_external_ids:
            return {}

        rows = self._db.execute(
            select(StationRecord.external_id, StationHistoricalChangeStatisticRecord)
            .join(
                StationHistoricalChangeStatisticRecord,
                StationHistoricalChangeStatisticRecord.station_id == StationRecord.id,
            )
            .where(StationRecord.external_id.in_(station_external_ids))
            .where(StationHistoricalChangeStatisticRecord.parameter == parameter)
            .where(StationHistoricalChangeStatisticRecord.window_hours == window_hours)
            .order_by(StationRecord.external_id, StationHistoricalChangeStatisticRecord.date)
        ).all()
        grouped: dict[str, list[HistoricalChangeStatistic]] = defaultdict(list)
        for external_id, row in rows:
            grouped[external_id].append(
                HistoricalChangeStatistic(
                    date=row.date,
                    window_hours=row.window_hours,
                    delta_value=row.delta_value,
                    observation_count=row.observation_count,
                )
            )
        return grouped

    def upsert_overview_snapshots(
        self,
        *,
        generated_at: datetime,
        stations: list[OverviewStation],
    ) -> int:
        affected = 0
        for station in stations:
            statement = (
                insert(StationOverviewSnapshotRecord)
                .values(
                    station_id=None,
                    parameter=station.parameter,
                    generated_at=generated_at,
                    station_external_id=station.station_id,
                    station_name=station.station_name,
                    water_system=station.water_system,
                    latitude=station.latitude,
                    longitude=station.longitude,
                    current_value=station.current_value,
                    unit=station.unit,
                    measured_at=station.measured_at,
                    seasonal_percentile=station.seasonal_percentile,
                    seasonal_status=station.seasonal_status,
                    anomaly_score=station.anomaly_score,
                    anomaly_severity=station.anomaly_severity,
                    anomaly_status=station.anomaly_status,
                    anomaly_direction=station.anomaly_direction,
                    confidence=station.confidence,
                    data_quality_status=station.data_quality_status,
                    freshness_status=station.freshness_status,
                    is_rankable=station.is_rankable,
                    delta_24h=station.delta_24h,
                    primary_signal=_primary_signal_dict(station.primary_signal),
                    historical_years=station.historical_years,
                    historical_sample_size=station.historical_sample_size,
                    recent_measurement_count=station.recent_measurement_count,
                )
                .on_conflict_do_update(
                    constraint="uq_station_overview_snapshots_external_id_parameter",
                    set_={
                        "generated_at": generated_at,
                        "station_id": None,
                        "station_name": station.station_name,
                        "water_system": station.water_system,
                        "latitude": station.latitude,
                        "longitude": station.longitude,
                        "current_value": station.current_value,
                        "unit": station.unit,
                        "measured_at": station.measured_at,
                        "seasonal_percentile": station.seasonal_percentile,
                        "seasonal_status": station.seasonal_status,
                        "anomaly_score": station.anomaly_score,
                        "anomaly_severity": station.anomaly_severity,
                        "anomaly_status": station.anomaly_status,
                        "anomaly_direction": station.anomaly_direction,
                        "confidence": station.confidence,
                        "data_quality_status": station.data_quality_status,
                        "freshness_status": station.freshness_status,
                        "is_rankable": station.is_rankable,
                        "delta_24h": station.delta_24h,
                        "primary_signal": _primary_signal_dict(station.primary_signal),
                        "historical_years": station.historical_years,
                        "historical_sample_size": station.historical_sample_size,
                        "recent_measurement_count": station.recent_measurement_count,
                        "updated_at": datetime.now().astimezone(),
                    },
                )
            )
            result = self._db.execute(statement)
            affected += result.rowcount or 0
        return affected

    def latest_overview_generated_at(self, parameter: str) -> datetime | None:
        return self._db.scalar(
            select(StationOverviewSnapshotRecord.generated_at)
            .where(StationOverviewSnapshotRecord.parameter == parameter)
            .order_by(StationOverviewSnapshotRecord.generated_at.desc())
            .limit(1)
        )

    def list_overview_snapshots(self, parameter: str) -> list[OverviewStation]:
        rows = self._db.scalars(
            select(StationOverviewSnapshotRecord)
            .where(StationOverviewSnapshotRecord.parameter == parameter)
            .order_by(StationOverviewSnapshotRecord.station_external_id)
        ).all()
        return [_overview_station_from_record(row) for row in rows]


def _merge_daily_source_metadata(
    measurements: list[MeasurementRecord],
) -> dict[str, str | int | None]:
    first = measurements[0]
    return {
        "source_station_code": first.source_station_code,
        "source_unit": first.source_unit,
        "observation_count": len(measurements),
    }


def _measurement_rows(
    station_record_id: int,
    measurements: list[Measurement],
) -> list[dict[str, object]]:
    rows_by_key: dict[tuple[int, str, datetime], dict[str, object]] = {}
    for measurement in measurements:
        rows_by_key[(station_record_id, measurement.parameter, measurement.measured_at)] = {
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
    return list(rows_by_key.values())


def _chunks[T](values: list[T], size: int):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _primary_signal_dict(signal: OverviewPrimarySignal | None) -> dict[str, object] | None:
    if signal is None:
        return None
    return {
        "type": signal.type,
        "direction": signal.direction,
        "value": signal.value,
        "unit": signal.unit,
        "percentile": signal.percentile,
        "score": signal.score,
        "message": signal.message,
    }


def _primary_signal_from_dict(value: dict[str, object] | None) -> OverviewPrimarySignal | None:
    if value is None:
        return None
    return OverviewPrimarySignal(
        type=str(value["type"]),
        direction=value["direction"] if isinstance(value.get("direction"), str) else None,
        value=value["value"] if isinstance(value.get("value"), int | float) else None,
        unit=value["unit"] if isinstance(value.get("unit"), str) else None,
        percentile=(
            value["percentile"] if isinstance(value.get("percentile"), int | float) else None
        ),
        score=value["score"] if isinstance(value.get("score"), int) else None,
        message=str(value["message"]),
    )


def _overview_station_from_record(row: StationOverviewSnapshotRecord) -> OverviewStation:
    return OverviewStation(
        station_id=row.station_external_id,
        station_name=row.station_name,
        water_system=row.water_system,
        latitude=row.latitude,
        longitude=row.longitude,
        current_value=row.current_value,
        unit=row.unit,
        measured_at=row.measured_at,
        parameter=row.parameter,
        seasonal_percentile=row.seasonal_percentile,
        seasonal_status=row.seasonal_status,
        anomaly_score=row.anomaly_score,
        anomaly_severity=row.anomaly_severity,
        anomaly_status=row.anomaly_status,
        anomaly_direction=row.anomaly_direction,
        confidence=row.confidence,
        data_quality_status=row.data_quality_status,
        freshness_status=row.freshness_status,
        is_rankable=row.is_rankable,
        delta_24h=row.delta_24h,
        primary_signal=_primary_signal_from_dict(row.primary_signal),
        historical_years=row.historical_years,
        historical_sample_size=row.historical_sample_size,
        recent_measurement_count=row.recent_measurement_count,
    )
