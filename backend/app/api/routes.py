from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db, get_rws_client
from app.clients.rws.client import RwsClient
from app.config import Settings
from app.domain.anomaly import AnomalyConfig
from app.domain.curated_stations import CURATED_STATION_BY_ID, CURATED_STATION_IDS
from app.domain.seasonal import SeasonalConfig
from app.exceptions import StationNotFound
from app.repositories.water import WaterRepository
from app.schemas.stations import (
    AnomalyDataQualityPayload,
    AnomalyResultPayload,
    AnomalySignalPayload,
    CurrentMeasurement,
    MapStationPayload,
    MeasurementPoint,
    OverviewCoveragePayload,
    OverviewPayload,
    OverviewPrimarySignalPayload,
    OverviewStationPayload,
    OverviewSummaryPayload,
    SeasonalContextPayload,
    SeasonalReferencePeriod,
    SeasonalReferenceValues,
    StationAnomalyPayload,
    StationDetail,
    StationSeasonalContext,
    StationSummary,
)
from app.services.anomaly import AnomalyService
from app.services.overview import OVERVIEW_FILTERS, OVERVIEW_SORTS, OverviewService
from app.services.seasonal import SeasonalContextService
from app.services.water import WaterService

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stations", response_model=list[StationSummary])
async def list_stations(
    rws_client: Annotated[RwsClient, Depends(get_rws_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    service = WaterService(
        rws_client,
        active_station_max_age_hours=settings.active_station_max_age_hours,
        active_station_recent_check_concurrency=settings.active_station_recent_check_concurrency,
        active_station_verify_recent_measurements=settings.active_station_verify_recent_measurements,
    )
    return [_station_summary_payload(station) for station in await service.list_stations()]


@router.get("/map-stations", response_model=list[MapStationPayload])
async def list_map_stations(
    rws_client: Annotated[RwsClient, Depends(get_rws_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    db: Annotated[Session, Depends(get_db)],
    parameter: str = "water_level",
):
    repository = WaterRepository(db)
    water_service = WaterService(
        rws_client,
        use_fallback_measurements=False,
        active_station_max_age_hours=settings.active_station_max_age_hours,
        active_station_recent_check_concurrency=settings.active_station_recent_check_concurrency,
        active_station_verify_recent_measurements=settings.active_station_verify_recent_measurements,
    )
    stations = await water_service.list_stations()
    overview_service = OverviewService(
        water_service=water_service,
        repository=repository,
        seasonal_config=SeasonalConfig(
            window_days=settings.seasonal_window_days,
            min_sample_size=settings.seasonal_min_sample_size,
            min_years=settings.seasonal_min_years,
        ),
        anomaly_config=AnomalyConfig(
            seasonal_window_days=settings.seasonal_window_days,
            delta_tolerance_minutes=settings.anomaly_delta_tolerance_minutes,
            recent_window_hours=settings.anomaly_recent_window_hours,
            stale_after_minutes=settings.anomaly_stale_after_minutes,
        ),
        cache_ttl=timedelta(minutes=settings.overview_cache_ttl_minutes),
        recent_measurement_concurrency=settings.active_station_recent_check_concurrency,
    )
    await overview_service.get_overview(parameter=parameter, limit=200)
    try:
        snapshots = {
            station.station_id: station
            for station in repository.list_overview_snapshots(parameter)
        }
    except SQLAlchemyError:
        repository.rollback()
        snapshots = {}
    return [
        _map_station_payload(station, snapshots.get(station.id))
        for station in stations
    ]


@router.get("/overview", response_model=OverviewPayload)
async def get_overview(
    rws_client: Annotated[RwsClient, Depends(get_rws_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    db: Annotated[Session, Depends(get_db)],
    parameter: str = "water_level",
    filter: Annotated[str, Query(pattern=f"^({'|'.join(sorted(OVERVIEW_FILTERS))})$")] = "all",
    sort: Annotated[str, Query(pattern=f"^({'|'.join(sorted(OVERVIEW_SORTS))})$")] = (
        "anomaly_score"
    ),
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
):
    repository = WaterRepository(db)
    result = await OverviewService(
        water_service=WaterService(
            rws_client,
            use_fallback_measurements=False,
            active_station_max_age_hours=settings.active_station_max_age_hours,
            active_station_recent_check_concurrency=(
                settings.active_station_recent_check_concurrency
            ),
            active_station_verify_recent_measurements=(
                settings.active_station_verify_recent_measurements
            ),
        ),
        repository=repository,
        seasonal_config=SeasonalConfig(
            window_days=settings.seasonal_window_days,
            min_sample_size=settings.seasonal_min_sample_size,
            min_years=settings.seasonal_min_years,
        ),
        anomaly_config=AnomalyConfig(
            seasonal_window_days=settings.seasonal_window_days,
            delta_tolerance_minutes=settings.anomaly_delta_tolerance_minutes,
            recent_window_hours=settings.anomaly_recent_window_hours,
            stale_after_minutes=settings.anomaly_stale_after_minutes,
        ),
        cache_ttl=timedelta(minutes=settings.overview_cache_ttl_minutes),
        recent_measurement_concurrency=settings.active_station_recent_check_concurrency,
    ).get_overview(
        parameter=parameter,
        overview_filter=filter,
        sort=sort,
        limit=limit or settings.overview_default_limit,
    )
    return OverviewPayload(
        generated_at=result.generated_at,
        summary=OverviewSummaryPayload(
            stations_monitored=result.summary.stations_monitored,
            high_or_extreme_anomalies=result.summary.high_or_extreme_anomalies,
            extreme_anomalies=result.summary.extreme_anomalies,
            rapidly_rising=result.summary.rapidly_rising,
            rapidly_falling=result.summary.rapidly_falling,
            data_limited_or_stale=result.summary.data_limited_or_stale,
        ),
        coverage=OverviewCoveragePayload(
            historical_context_stations=result.coverage.historical_context_stations,
            insufficient_data_stations=result.coverage.insufficient_data_stations,
            stale_stations=result.coverage.stale_stations,
            rankable_stations=result.coverage.rankable_stations,
        ),
        stations=[_overview_station_payload(station) for station in result.stations],
    )


@router.get("/stations/{station_id}", response_model=StationDetail)
async def get_station(
    station_id: str,
    rws_client: Annotated[RwsClient, Depends(get_rws_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    service = WaterService(
        rws_client,
        active_station_max_age_hours=settings.active_station_max_age_hours,
        active_station_recent_check_concurrency=settings.active_station_recent_check_concurrency,
        active_station_verify_recent_measurements=settings.active_station_verify_recent_measurements,
    )
    station = await service.get_station(station_id)
    return StationDetail(
        **_station_summary_payload(station).model_dump(),
        metadata=station.metadata,
    )


@router.get("/stations/{station_id}/measurements", response_model=list[MeasurementPoint])
async def get_measurements(
    station_id: str,
    rws_client: Annotated[RwsClient, Depends(get_rws_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    hours: Annotated[int, Query(ge=1, le=168)] = 48,
):
    service = WaterService(
        rws_client,
        use_fallback_measurements=settings.rws_use_fallback_measurements,
    )
    return await service.get_measurements(station_id, hours)


@router.get("/stations/{station_id}/seasonal-context", response_model=StationSeasonalContext)
async def get_seasonal_context(
    station_id: str,
    rws_client: Annotated[RwsClient, Depends(get_rws_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    db: Annotated[Session, Depends(get_db)],
    parameter: str = "water_level",
    current_value: float | None = None,
    current_unit: str | None = None,
    measured_at: datetime | None = None,
):
    if station_id not in CURATED_STATION_IDS:
        raise StationNotFound(f"Station {station_id!r} was not found")

    current_measurements = None
    if current_value is not None and measured_at is not None:
        current_measurements = await WaterService(
            rws_client,
            use_fallback_measurements=False,
        ).get_measurements(station_id, 24)

    context = SeasonalContextService(
        WaterRepository(db),
        SeasonalConfig(
            window_days=settings.seasonal_window_days,
            min_sample_size=settings.seasonal_min_sample_size,
            min_years=settings.seasonal_min_years,
        ),
    ).get_context_for_current(
        station_id=station_id,
        current_value=current_value,
        current_measurements=current_measurements,
        measured_at=measured_at,
        parameter=parameter,
    )
    return StationSeasonalContext(
        station_id=station_id,
        parameter=parameter,
        current=CurrentMeasurement(
            value=current_value,
            unit=current_unit,
            measured_at=measured_at,
        ),
        seasonal_context=SeasonalContextPayload(
            percentile=context.percentile,
            status=context.status,
            sample_size=context.sample_size,
            years_used=context.years_used,
            historical_sample_size=context.historical_sample_size,
            historical_years=context.historical_years,
            reference_period=SeasonalReferencePeriod(
                window_days=context.reference_period.window_days,
                first_year=context.reference_period.first_year,
                last_year=context.reference_period.last_year,
            ),
            reference_values=(
                SeasonalReferenceValues(
                    p05=context.reference_values.p05,
                    p25=context.reference_values.p25,
                    p50=context.reference_values.p50,
                    p75=context.reference_values.p75,
                    p95=context.reference_values.p95,
                )
                if context.reference_values
                else None
            ),
        ),
    )


@router.get("/stations/{station_id}/anomaly", response_model=StationAnomalyPayload)
async def get_station_anomaly(
    station_id: str,
    rws_client: Annotated[RwsClient, Depends(get_rws_client)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    db: Annotated[Session, Depends(get_db)],
    parameter: str = "water_level",
):
    if station_id not in CURATED_STATION_IDS:
        raise StationNotFound(f"Station {station_id!r} was not found")

    repository = WaterRepository(db)
    seasonal_config = SeasonalConfig(
        window_days=settings.seasonal_window_days,
        min_sample_size=settings.seasonal_min_sample_size,
        min_years=settings.seasonal_min_years,
    )
    result = await AnomalyService(
        water_service=WaterService(
            rws_client,
            use_fallback_measurements=False,
            active_station_max_age_hours=settings.active_station_max_age_hours,
            active_station_recent_check_concurrency=(
                settings.active_station_recent_check_concurrency
            ),
            active_station_verify_recent_measurements=(
                settings.active_station_verify_recent_measurements
            ),
        ),
        seasonal_service=SeasonalContextService(repository, seasonal_config),
        repository=repository,
        anomaly_config=AnomalyConfig(
            seasonal_window_days=settings.seasonal_window_days,
            delta_tolerance_minutes=settings.anomaly_delta_tolerance_minutes,
            recent_window_hours=settings.anomaly_recent_window_hours,
            stale_after_minutes=settings.anomaly_stale_after_minutes,
        ),
    ).get_station_anomaly(station_id, parameter)

    return StationAnomalyPayload(
        station_id=result.station_id,
        parameter=result.parameter,
        evaluated_at=result.evaluated_at,
        current=CurrentMeasurement(
            value=result.current.value,
            unit=result.current.unit,
            measured_at=result.current.measured_at,
        ),
        anomaly=AnomalyResultPayload(
            status=result.anomaly.status,
            score=result.anomaly.score,
            severity=result.anomaly.severity,
            is_anomalous=result.anomaly.is_anomalous,
            confidence=result.anomaly.confidence,
            signals=[_anomaly_signal_payload(signal) for signal in result.anomaly.signals],
        ),
        data_quality=AnomalyDataQualityPayload(
            status=result.data_quality.status,
            signals=[_anomaly_signal_payload(signal) for signal in result.data_quality.signals],
            historical_years=result.data_quality.historical_years,
            historical_sample_size=result.data_quality.historical_sample_size,
            recent_measurement_count=result.data_quality.recent_measurement_count,
            largest_recent_gap_minutes=result.data_quality.largest_recent_gap_minutes,
        ),
    )


def _anomaly_signal_payload(signal) -> AnomalySignalPayload:
    return AnomalySignalPayload(
        type=signal.type,
        category=signal.category,
        score=signal.score,
        direction=signal.direction,
        value=signal.value,
        unit=signal.unit,
        percentile=signal.percentile,
        message=signal.message,
    )


def _station_summary_payload(station) -> StationSummary:
    curated = CURATED_STATION_BY_ID.get(station.id)
    return StationSummary(
        id=station.id,
        name=station.name,
        latitude=station.latitude,
        longitude=station.longitude,
        latest_value=station.latest_value,
        unit=station.unit,
        measured_at=station.measured_at,
        parameter=station.parameter,
        status=station.status,
        quality_code=station.quality_code,
        water_system=(
            curated.water_system if curated else _metadata_string(station.metadata, "water_system")
        ),
        station_group=(
            curated.station_group
            if curated
            else _metadata_string(station.metadata, "station_group")
        ),
        station_group_label=(
            curated.station_group_label
            if curated
            else _metadata_string(station.metadata, "station_group_label")
        ),
        significance=(
            curated.significance if curated else _metadata_string(station.metadata, "significance")
        ),
    )


def _map_station_payload(station, overview_station) -> MapStationPayload:
    base = _station_summary_payload(station).model_dump()
    if overview_station is None:
        return MapStationPayload(**base)
    return MapStationPayload(
        **base,
        seasonal_percentile=overview_station.seasonal_percentile,
        seasonal_status=overview_station.seasonal_status,
        anomaly_score=overview_station.anomaly_score,
        anomaly_severity=overview_station.anomaly_severity,
        anomaly_status=overview_station.anomaly_status,
        anomaly_direction=overview_station.anomaly_direction,
        confidence=overview_station.confidence,
        data_quality_status=overview_station.data_quality_status,
        freshness_status=overview_station.freshness_status,
        delta_24h=overview_station.delta_24h,
        primary_signal=(
            OverviewPrimarySignalPayload(
                type=overview_station.primary_signal.type,
                direction=overview_station.primary_signal.direction,
                value=overview_station.primary_signal.value,
                unit=overview_station.primary_signal.unit,
                percentile=overview_station.primary_signal.percentile,
                score=overview_station.primary_signal.score,
                message=overview_station.primary_signal.message,
            )
            if overview_station.primary_signal
            else None
        ),
    )


def _metadata_string(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _overview_station_payload(station) -> OverviewStationPayload:
    return OverviewStationPayload(
        station_id=station.station_id,
        station_name=station.station_name,
        water_system=station.water_system,
        latitude=station.latitude,
        longitude=station.longitude,
        current_value=station.current_value,
        unit=station.unit,
        measured_at=station.measured_at,
        parameter=station.parameter,
        seasonal_percentile=station.seasonal_percentile,
        seasonal_status=station.seasonal_status,
        anomaly_score=station.anomaly_score,
        anomaly_severity=station.anomaly_severity,
        anomaly_status=station.anomaly_status,
        anomaly_direction=station.anomaly_direction,
        confidence=station.confidence,
        data_quality_status=station.data_quality_status,
        freshness_status=station.freshness_status,
        delta_24h=station.delta_24h,
        primary_signal=(
            OverviewPrimarySignalPayload(
                type=station.primary_signal.type,
                direction=station.primary_signal.direction,
                value=station.primary_signal.value,
                unit=station.primary_signal.unit,
                percentile=station.primary_signal.percentile,
                score=station.primary_signal.score,
                message=station.primary_signal.message,
            )
            if station.primary_signal
            else None
        ),
    )
