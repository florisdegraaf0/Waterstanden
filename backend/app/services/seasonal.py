import logging
from dataclasses import replace
from datetime import datetime
from statistics import mean

from sqlalchemy.exc import SQLAlchemyError

from app.domain.models import DailyStatistic, Measurement, SeasonalContext, Station
from app.domain.parameters import validate_parameter
from app.domain.seasonal import SeasonalConfig, calculate_seasonal_context
from app.repositories.water import WaterRepository

logger = logging.getLogger(__name__)


class SeasonalContextService:
    def __init__(self, repository: WaterRepository, config: SeasonalConfig) -> None:
        self._repository = repository
        self._config = config

    def get_context(self, station: Station, parameter: str = "water_level") -> SeasonalContext:
        parameter = validate_parameter(parameter)
        current = (station.parameters or {}).get(parameter)
        current_value = current.value if current else station.latest_value
        measured_at = current.measured_at if current else station.measured_at
        if current_value is None or measured_at is None:
            return SeasonalContext(
                status="insufficient_data",
                percentile=None,
                sample_size=0,
                years_used=0,
                historical_sample_size=0,
                historical_years=0,
                reference_period=_empty_reference_period(self._config.window_days),
                reference_values=None,
            )

        daily_values, error = self._list_daily_statistics_or_empty(station.id, parameter)
        if error is not None:
            return _historical_data_unavailable(self._config.window_days)

        return calculate_seasonal_context(
            current_value=current_value,
            current_date=measured_at.date(),
            historical_daily_values=daily_values,
            config=self._config,
        )

    def get_context_for_current(
        self,
        *,
        station_id: str,
        current_value: float | None,
        measured_at: datetime | None,
        current_measurements: list[Measurement] | None = None,
        parameter: str = "water_level",
    ) -> SeasonalContext:
        parameter = validate_parameter(parameter)
        if current_value is None or measured_at is None:
            return SeasonalContext(
                status="insufficient_data",
                percentile=None,
                sample_size=0,
                years_used=0,
                historical_sample_size=0,
                historical_years=0,
                reference_period=_empty_reference_period(self._config.window_days),
                reference_values=None,
            )

        daily_values, error = self._list_daily_statistics_or_empty(station_id, parameter)
        if error is not None:
            return _historical_data_unavailable(self._config.window_days)

        comparison_value = current_value
        comparison_daily_values = daily_values
        if current_measurements is not None:
            comparison_value = _mean_measurement_value(current_measurements, parameter)
            comparison_daily_values = _use_daily_mean_values(daily_values)

        if comparison_value is None:
            return SeasonalContext(
                status="insufficient_data",
                percentile=None,
                sample_size=0,
                years_used=0,
                historical_sample_size=len(daily_values),
                historical_years=len({value.date.year for value in daily_values}),
                reference_period=_empty_reference_period(self._config.window_days),
                reference_values=None,
            )

        return calculate_seasonal_context(
            current_value=comparison_value,
            current_date=measured_at.date(),
            historical_daily_values=comparison_daily_values,
            config=self._config,
        )

    def _list_daily_statistics_or_empty(self, station_id: str, parameter: str):
        try:
            return self._repository.list_daily_statistics(station_id, parameter), None
        except SQLAlchemyError as exc:
            logger.warning(
                "Historical seasonal data query failed",
                extra={"station_id": station_id, "parameter": parameter},
                exc_info=exc,
            )
            return [], exc


def _empty_reference_period(window_days: int):
    from app.domain.models import ReferencePeriod

    return ReferencePeriod(window_days=window_days, first_year=None, last_year=None)


def _historical_data_unavailable(window_days: int) -> SeasonalContext:
    return SeasonalContext(
        status="historical_data_unavailable",
        percentile=None,
        sample_size=0,
        years_used=0,
        historical_sample_size=0,
        historical_years=0,
        reference_period=_empty_reference_period(window_days),
        reference_values=None,
    )


def _mean_measurement_value(
    measurements: list[Measurement],
    parameter: str,
) -> float | None:
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
