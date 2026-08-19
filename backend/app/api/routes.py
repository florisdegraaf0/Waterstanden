from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db, get_rws_client
from app.clients.rws.client import RwsClient
from app.config import Settings
from app.domain.anomaly import AnomalyConfig
from app.domain.curated_stations import CURATED_STATION_IDS
from app.domain.seasonal import SeasonalConfig
from app.exceptions import StationNotFound
from app.repositories.water import WaterRepository
from app.schemas.stations import (
    AnomalyDataQualityPayload,
    AnomalyResultPayload,
    AnomalySignalPayload,
    CurrentMeasurement,
    MeasurementPoint,
    SeasonalContextPayload,
    SeasonalReferencePeriod,
    SeasonalReferenceValues,
    StationAnomalyPayload,
    StationDetail,
    StationSeasonalContext,
    StationSummary,
)
from app.services.anomaly import AnomalyService
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
    return await service.list_stations()


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
    return await service.get_station(station_id)


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
