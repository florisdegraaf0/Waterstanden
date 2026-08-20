from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from statistics import mean

from sqlalchemy.exc import SQLAlchemyError

from app.domain.anomaly import (
    DELTA_WINDOW_HOURS,
    AnomalyConfig,
    build_anomaly_result,
    calculate_change_reference,
    calculate_recent_features,
    detect_data_quality,
)
from app.domain.curated_stations import CURATED_STATION_BY_ID
from app.domain.models import DailyStatistic, Measurement, Station
from app.domain.overview import (
    OverviewCoverage,
    OverviewPrimarySignal,
    OverviewResult,
    OverviewStation,
    OverviewSummary,
)
from app.domain.seasonal import SeasonalConfig, calculate_seasonal_context
from app.exceptions import ExternalServiceError
from app.repositories.water import WaterRepository
from app.services.water import WaterService

logger = logging.getLogger(__name__)

OVERVIEW_FILTERS = {
    "all",
    "high_extreme",
    "unusually_high",
    "unusually_low",
    "rapidly_rising",
    "rapidly_falling",
}
OVERVIEW_SORTS = {
    "anomaly_score",
    "largest_24h_rise",
    "largest_24h_fall",
    "seasonal_unusualness",
}


class OverviewService:
    def __init__(
        self,
        *,
        water_service: WaterService,
        repository: WaterRepository,
        seasonal_config: SeasonalConfig,
        anomaly_config: AnomalyConfig,
        cache_ttl: timedelta,
        recent_measurement_concurrency: int,
    ) -> None:
        self._water_service = water_service
        self._repository = repository
        self._seasonal_config = seasonal_config
        self._anomaly_config = anomaly_config
        self._cache_ttl = cache_ttl
        self._recent_measurement_concurrency = recent_measurement_concurrency

    async def get_overview(
        self,
        *,
        parameter: str = "water_level",
        overview_filter: str = "all",
        sort: str = "anomaly_score",
        limit: int = 50,
    ) -> OverviewResult:
        if overview_filter not in OVERVIEW_FILTERS:
            overview_filter = "all"
        if sort not in OVERVIEW_SORTS:
            sort = "anomaly_score"

        try:
            generated_at = self._repository.latest_overview_generated_at(parameter)
        except SQLAlchemyError as exc:
            logger.warning(
                "Overview cache timestamp query failed",
                extra={"parameter": parameter},
                exc_info=exc,
            )
            self._repository.rollback()
            return _build_overview_result(
                generated_at=datetime.now(UTC),
                stations=[],
                overview_filter=overview_filter,
                sort=sort,
                limit=limit,
            )

        now = datetime.now(UTC)
        if generated_at is None or generated_at < now - self._cache_ttl:
            try:
                generated_at = await self.refresh(parameter=parameter, generated_at=now)
            except (ExternalServiceError, SQLAlchemyError) as exc:
                logger.warning(
                    "Overview refresh failed",
                    extra={"parameter": parameter},
                    exc_info=exc,
                )
                self._repository.rollback()

        try:
            snapshots = self._repository.list_overview_snapshots(parameter)
        except SQLAlchemyError as exc:
            logger.warning(
                "Overview snapshot query failed",
                extra={"parameter": parameter},
                exc_info=exc,
            )
            self._repository.rollback()
            snapshots = []

        if generated_at is None:
            generated_at = now
        return _build_overview_result(
            generated_at=generated_at,
            stations=snapshots,
            overview_filter=overview_filter,
            sort=sort,
            limit=limit,
        )

    async def refresh(self, *, parameter: str = "water_level", generated_at: datetime) -> datetime:
        active_stations = await self._water_service.list_stations()
        station_ids = [station.id for station in active_stations]
        daily_statistics = self._repository.list_daily_statistics_for_stations(
            station_ids,
            parameter,
        )
        change_statistics = self._repository.list_historical_change_statistics_for_stations(
            station_ids,
            parameter,
            DELTA_WINDOW_HOURS,
        )
        recent_measurements = await self._recent_measurements_by_station(active_stations)

        overview_stations = [
            _build_station_overview(
                station=station,
                parameter=parameter,
                recent_measurements=recent_measurements.get(station.id, []),
                daily_statistics=daily_statistics.get(station.id, []),
                change_statistics=change_statistics.get(station.id, []),
                seasonal_config=self._seasonal_config,
                anomaly_config=self._anomaly_config,
                evaluated_at=generated_at,
            )
            for station in active_stations
        ]
        self._repository.upsert_overview_snapshots(
            generated_at=generated_at,
            stations=overview_stations,
        )
        self._repository.commit()
        return generated_at

    async def _recent_measurements_by_station(
        self,
        stations: list[Station],
    ) -> dict[str, list[Measurement]]:
        semaphore = asyncio.Semaphore(self._recent_measurement_concurrency)

        async def fetch(station: Station) -> tuple[str, list[Measurement]]:
            async with semaphore:
                try:
                    return (
                        station.id,
                        await self._water_service.get_measurements(
                            station.id,
                            self._anomaly_config.recent_window_hours,
                        ),
                    )
                except ExternalServiceError as exc:
                    logger.warning(
                        "Recent measurements unavailable for overview",
                        extra={"station_id": station.id},
                        exc_info=exc,
                    )
                    return station.id, []

        return dict(await asyncio.gather(*(fetch(station) for station in stations)))


def _build_station_overview(
    *,
    station: Station,
    parameter: str,
    recent_measurements: list[Measurement],
    daily_statistics: list[DailyStatistic],
    change_statistics: list,
    seasonal_config: SeasonalConfig,
    anomaly_config: AnomalyConfig,
    evaluated_at: datetime,
) -> OverviewStation:
    current = _current_measurement(station, evaluated_at)
    current_24h_measurements = [
        measurement
        for measurement in recent_measurements
        if measurement.measured_at >= current.measured_at - timedelta(hours=24)
    ]
    comparison_value = _mean_measurement_value(current_24h_measurements, parameter)
    seasonal_context = (
        calculate_seasonal_context(
            current_value=comparison_value,
            current_date=current.measured_at.date(),
            historical_daily_values=_use_daily_mean_values(daily_statistics),
            config=seasonal_config,
        )
        if comparison_value is not None
        else calculate_seasonal_context(
            current_value=current.value,
            current_date=current.measured_at.date(),
            historical_daily_values=daily_statistics,
            config=seasonal_config,
        )
    )
    features = calculate_recent_features(
        current=current,
        recent_measurements=recent_measurements,
        evaluated_at=evaluated_at,
        config=anomaly_config,
        parameter=parameter,
    )
    data_quality_status, data_quality_signals = detect_data_quality(
        current=current,
        recent_measurements=recent_measurements,
        features=features,
        config=anomaly_config,
    )
    change_reference = calculate_change_reference(
        current_delta=features.delta_24h,
        current_date=current.measured_at.date(),
        historical_changes=change_statistics,
        config=anomaly_config,
    )
    anomaly, data_quality = build_anomaly_result(
        level_percentile=seasonal_context.percentile,
        level_status=seasonal_context.status,
        level_sample_size=seasonal_context.sample_size,
        level_years_used=seasonal_context.years_used,
        level_value=current.value,
        level_unit=current.unit,
        change_reference=change_reference,
        delta_24h=features.delta_24h,
        features=features,
        data_quality_status=data_quality_status,
        data_quality_signals=data_quality_signals,
    )
    primary_signal = _primary_signal(anomaly.signals)
    freshness_status = "stale" if data_quality_status == "data_quality_anomaly" else "current"
    is_rankable = (
        anomaly.score is not None
        and anomaly.status == "ok"
        and data_quality_status != "data_quality_anomaly"
    )
    return OverviewStation(
        station_id=station.id,
        station_name=station.name,
        water_system=str(station.metadata.get("water_system") or "Unknown"),
        latitude=station.latitude,
        longitude=station.longitude,
        current_value=station.latest_value,
        unit=station.unit,
        measured_at=station.measured_at,
        parameter=parameter,
        seasonal_percentile=seasonal_context.percentile,
        seasonal_status=seasonal_context.status,
        anomaly_score=anomaly.score,
        anomaly_severity=anomaly.severity,
        anomaly_status=anomaly.status,
        anomaly_direction=primary_signal.direction if primary_signal else None,
        confidence=anomaly.confidence,
        data_quality_status=data_quality.status,
        freshness_status=freshness_status,
        is_rankable=is_rankable,
        delta_24h=features.delta_24h,
        primary_signal=primary_signal,
        historical_years=data_quality.historical_years,
        historical_sample_size=data_quality.historical_sample_size,
        recent_measurement_count=data_quality.recent_measurement_count,
    )


def _build_overview_result(
    *,
    generated_at: datetime,
    stations: list[OverviewStation],
    overview_filter: str,
    sort: str,
    limit: int,
) -> OverviewResult:
    rankable = [station for station in stations if station.is_rankable]
    summary = OverviewSummary(
        stations_monitored=len(stations),
        high_or_extreme_anomalies=sum(
            1 for station in rankable if station.anomaly_severity in {"high", "extreme"}
        ),
        extreme_anomalies=sum(1 for station in rankable if station.anomaly_severity == "extreme"),
        rapidly_rising=sum(1 for station in rankable if _has_change_direction(station, "rising")),
        rapidly_falling=sum(1 for station in rankable if _has_change_direction(station, "falling")),
        data_limited_or_stale=sum(
            1
            for station in stations
            if station.anomaly_score is None or station.freshness_status == "stale"
        ),
    )
    coverage = OverviewCoverage(
        historical_context_stations=sum(
            1 for station in stations if station.anomaly_score is not None
        ),
        insufficient_data_stations=sum(
            1
            for station in stations
            if station.anomaly_status in {"insufficient_data", "historical_data_unavailable"}
        ),
        stale_stations=sum(1 for station in stations if station.freshness_status == "stale"),
        rankable_stations=len(rankable),
    )
    filtered = [_station for _station in rankable if _matches_filter(_station, overview_filter)]
    ordered = sorted(filtered, key=lambda station: _sort_key(station, sort))
    return OverviewResult(
        generated_at=generated_at,
        summary=summary,
        coverage=coverage,
        stations=ordered[:limit],
    )


def _current_measurement(station: Station, fallback_time: datetime) -> Measurement:
    return Measurement(
        measured_at=station.measured_at or fallback_time,
        value=station.latest_value or 0.0,
        unit=station.unit or "m",
        parameter=station.parameter,
        quality_code=station.quality_code,
    )


def _mean_measurement_value(measurements: list[Measurement], parameter: str) -> float | None:
    values = [
        measurement.value
        for measurement in measurements
        if measurement.parameter == parameter
    ]
    if not values:
        return None
    return mean(values)


def _use_daily_mean_values(daily_values: list[DailyStatistic]) -> list[DailyStatistic]:
    return [replace(value, value=value.mean_value) for value in daily_values]


def _primary_signal(signals) -> OverviewPrimarySignal | None:
    hydrological = [signal for signal in signals if signal.category == "hydrological"]
    if not hydrological:
        return None
    signal = max(hydrological, key=lambda value: value.score or 0)
    return OverviewPrimarySignal(
        type=signal.type,
        direction=signal.direction,
        value=signal.value,
        unit=signal.unit,
        percentile=signal.percentile,
        score=signal.score,
        message=signal.message,
    )


def _matches_filter(station: OverviewStation, overview_filter: str) -> bool:
    if overview_filter == "high_extreme":
        return station.anomaly_severity in {"high", "extreme"}
    if overview_filter == "unusually_high":
        return station.seasonal_status in {"unusually_high", "extremely_high"}
    if overview_filter == "unusually_low":
        return station.seasonal_status in {"unusually_low", "extremely_low"}
    if overview_filter == "rapidly_rising":
        return _has_change_direction(station, "rising")
    if overview_filter == "rapidly_falling":
        return _has_change_direction(station, "falling")
    return True


def _sort_key(station: OverviewStation, sort: str) -> tuple[float, int, int]:
    sort_order = CURATED_STATION_BY_ID[station.station_id].sort_order
    measured_at = int(station.measured_at.timestamp()) if station.measured_at else 0
    if sort == "largest_24h_rise":
        primary = -(station.delta_24h or 0)
    elif sort == "largest_24h_fall":
        primary = station.delta_24h or 0
    elif sort == "seasonal_unusualness":
        primary = -_seasonal_unusualness(station)
    else:
        primary = -(station.anomaly_score or 0)
    return (primary, -measured_at, sort_order)


def _seasonal_unusualness(station: OverviewStation) -> float:
    if station.seasonal_percentile is None:
        return -1
    return abs(station.seasonal_percentile - 50) * 2


def _has_change_direction(station: OverviewStation, direction: str) -> bool:
    signal = station.primary_signal
    return (
        signal is not None
        and signal.type == "rate_of_change_24h"
        and signal.direction == direction
    )
