from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_app_settings, get_rws_client
from app.clients.rws.client import RwsClient
from app.config import Settings
from app.schemas.stations import MeasurementPoint, StationDetail, StationSummary
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
