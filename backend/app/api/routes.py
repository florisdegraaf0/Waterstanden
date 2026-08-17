from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db, get_rws_client
from app.clients.rws.client import RwsClient
from app.config import Settings
from app.domain.seasonal import SeasonalConfig
from app.repositories.water import WaterRepository
from app.schemas.stations import (
    CurrentMeasurement,
    MeasurementPoint,
    SeasonalContextPayload,
    SeasonalReferencePeriod,
    SeasonalReferenceValues,
    StationDetail,
    StationSeasonalContext,
    StationSummary,
)
from app.services.seasonal import SeasonalContextService
from app.services.water import WaterService

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stations", response_model=list[StationSummary])
async def list_stations(rws_client: Annotated[RwsClient, Depends(get_rws_client)]):
    service = WaterService(rws_client)
    return await service.list_stations()


@router.get("/stations/{station_id}", response_model=StationDetail)
async def get_station(station_id: str, rws_client: Annotated[RwsClient, Depends(get_rws_client)]):
    service = WaterService(rws_client)
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
):
    station = await WaterService(rws_client).get_station(station_id)
    context = SeasonalContextService(
        WaterRepository(db),
        SeasonalConfig(
            window_days=settings.seasonal_window_days,
            min_sample_size=settings.seasonal_min_sample_size,
            min_years=settings.seasonal_min_years,
        ),
    ).get_context(station, parameter)
    return StationSeasonalContext(
        station_id=station.id,
        parameter=parameter,
        current=CurrentMeasurement(
            value=station.latest_value,
            unit=station.unit,
            measured_at=station.measured_at,
        ),
        seasonal_context=SeasonalContextPayload(
            percentile=context.percentile,
            status=context.status,
            sample_size=context.sample_size,
            years_used=context.years_used,
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
