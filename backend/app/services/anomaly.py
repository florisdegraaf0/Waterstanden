import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from app.domain.anomaly import (
    DELTA_WINDOW_HOURS,
    AnomalyConfig,
    build_anomaly_result,
    calculate_change_reference,
    calculate_recent_features,
    detect_data_quality,
)
from app.domain.models import Measurement, StationAnomaly
from app.domain.parameters import parameter_metadata, validate_parameter
from app.repositories.water import WaterRepository
from app.services.seasonal import SeasonalContextService
from app.services.water import WaterService

logger = logging.getLogger(__name__)


class AnomalyService:
    def __init__(
        self,
        *,
        water_service: WaterService,
        seasonal_service: SeasonalContextService,
        repository: WaterRepository,
        anomaly_config: AnomalyConfig,
    ) -> None:
        self._water_service = water_service
        self._seasonal_service = seasonal_service
        self._repository = repository
        self._anomaly_config = anomaly_config

    async def get_station_anomaly(
        self,
        station_id: str,
        parameter: str = "water_level",
    ) -> StationAnomaly:
        parameter = validate_parameter(parameter)
        station = await self._water_service.get_station(station_id)
        evaluated_at = datetime.now(UTC)
        current = _current_measurement(station, parameter)
        recent_measurements = await self._water_service.get_measurements(
            station_id,
            self._anomaly_config.recent_window_hours,
            parameter=parameter,
        )
        current_24h_measurements = [
            measurement
            for measurement in recent_measurements
            if measurement.measured_at >= current.measured_at - timedelta(hours=24)
        ]
        seasonal_context = self._seasonal_service.get_context_for_current(
            station_id=station_id,
            current_value=current.value,
            measured_at=current.measured_at,
            current_measurements=current_24h_measurements,
            parameter=parameter,
        )
        features = calculate_recent_features(
            current=current,
            recent_measurements=recent_measurements,
            evaluated_at=evaluated_at,
            config=self._anomaly_config,
            parameter=parameter,
        )
        data_quality_status, data_quality_signals = detect_data_quality(
            current=current,
            recent_measurements=recent_measurements,
            features=features,
            config=self._anomaly_config,
        )
        historical_changes = self._list_historical_changes_or_empty(station_id, parameter)
        change_reference = calculate_change_reference(
            current_delta=features.delta_24h,
            current_date=current.measured_at.date(),
            historical_changes=historical_changes,
            config=self._anomaly_config,
        )
        anomaly, data_quality = build_anomaly_result(
            level_percentile=seasonal_context.percentile,
            level_status=seasonal_context.status,
            level_sample_size=seasonal_context.sample_size,
            level_years_used=seasonal_context.years_used,
            level_value=current.value,
            level_unit=current.unit,
            parameter_label=parameter_metadata(parameter).label,
            change_reference=change_reference,
            delta_24h=features.delta_24h,
            delta_unit=current.unit,
            features=features,
            data_quality_status=data_quality_status,
            data_quality_signals=data_quality_signals,
        )
        return StationAnomaly(
            station_id=station_id,
            parameter=parameter,
            evaluated_at=evaluated_at,
            current=current,
            anomaly=anomaly,
            data_quality=data_quality,
        )

    def _list_historical_changes_or_empty(
        self,
        station_id: str,
        parameter: str,
    ):
        try:
            return self._repository.list_historical_change_statistics(
                station_id,
                parameter,
                DELTA_WINDOW_HOURS,
            )
        except SQLAlchemyError as exc:
            logger.warning(
                "Historical anomaly data query failed",
                extra={"station_id": station_id, "parameter": parameter},
                exc_info=exc,
            )
            return []


def _current_measurement(station, parameter: str) -> Measurement:
    station_parameters = station.parameters or {}
    selected = station_parameters.get(parameter)
    if selected is not None:
        return selected
    if station.latest_value is None or station.measured_at is None:
        return Measurement(
            measured_at=datetime.now(UTC),
            value=0.0,
            unit=parameter_metadata(parameter).default_unit,
            parameter=parameter,
            quality_code=station.quality_code,
        )
    return Measurement(
        measured_at=station.measured_at,
        value=station.latest_value,
        unit=station.unit or parameter_metadata(parameter).default_unit,
        parameter=parameter,
        quality_code=station.quality_code,
    )
