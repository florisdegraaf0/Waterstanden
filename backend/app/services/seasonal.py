from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from app.domain.models import SeasonalContext, Station
from app.domain.seasonal import SeasonalConfig, calculate_seasonal_context
from app.repositories.water import WaterRepository


class SeasonalContextService:
    def __init__(self, repository: WaterRepository, config: SeasonalConfig) -> None:
        self._repository = repository
        self._config = config

    def get_context(self, station: Station, parameter: str = "water_level") -> SeasonalContext:
        if station.latest_value is None or station.measured_at is None:
            return SeasonalContext(
                status="insufficient_data",
                percentile=None,
                sample_size=0,
                years_used=0,
                reference_period=_empty_reference_period(self._config.window_days),
                reference_values=None,
            )

        daily_values = self._list_daily_statistics_or_empty(station.id, parameter)
        return calculate_seasonal_context(
            current_value=station.latest_value,
            current_date=station.measured_at.date(),
            historical_daily_values=daily_values,
            config=self._config,
        )

    def get_context_for_current(
        self,
        *,
        station_id: str,
        current_value: float | None,
        measured_at: datetime | None,
        parameter: str = "water_level",
    ) -> SeasonalContext:
        if current_value is None or measured_at is None:
            return SeasonalContext(
                status="insufficient_data",
                percentile=None,
                sample_size=0,
                years_used=0,
                reference_period=_empty_reference_period(self._config.window_days),
                reference_values=None,
            )

        daily_values = self._list_daily_statistics_or_empty(station_id, parameter)
        return calculate_seasonal_context(
            current_value=current_value,
            current_date=measured_at.date(),
            historical_daily_values=daily_values,
            config=self._config,
        )

    def _list_daily_statistics_or_empty(self, station_id: str, parameter: str):
        try:
            return self._repository.list_daily_statistics(station_id, parameter)
        except SQLAlchemyError:
            return []


def _empty_reference_period(window_days: int):
    from app.domain.models import ReferencePeriod

    return ReferencePeriod(window_days=window_days, first_year=None, last_year=None)
