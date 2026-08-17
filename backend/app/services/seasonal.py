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

        daily_values = self._repository.list_daily_statistics(station.id, parameter)
        return calculate_seasonal_context(
            current_value=station.latest_value,
            current_date=station.measured_at.date(),
            historical_daily_values=daily_values,
            config=self._config,
        )


def _empty_reference_period(window_days: int):
    from app.domain.models import ReferencePeriod

    return ReferencePeriod(window_days=window_days, first_year=None, last_year=None)
